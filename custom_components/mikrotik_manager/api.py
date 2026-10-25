"""Thin read-only client for the MikroTik Manager REST API."""
from __future__ import annotations

from typing import Any

from aiohttp import ClientSession

from .logic import build_headers


class ManagerAuthError(Exception):
    """The token was rejected."""


class ManagerForbiddenError(ManagerAuthError):
    """403: the token is valid but lacks access to this endpoint."""


class ManagerClient:
    def __init__(
        self, session: ClientSession, base_url: str, token: str, verify_ssl: bool,
        site_id: int | str | None = None,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._headers = build_headers(token, site_id)
        self._ssl = None if verify_ssl else False

    async def get(self, path: str) -> Any:
        async with self._session.get(
            f"{self._base}{path}", headers=self._headers, ssl=self._ssl, timeout=20
        ) as resp:
            if resp.status == 403:
                raise ManagerForbiddenError(path)
            if resp.status == 401:
                raise ManagerAuthError(path)
            resp.raise_for_status()
            return await resp.json()

    async def summary(self) -> dict[str, Any]:
        return await self.get("/api/metrics/summary")

    async def devices(self) -> list[dict[str, Any]]:
        data = await self.get("/api/devices")
        return data if isinstance(data, list) else data.get("devices", [])

    async def ports(self, device_id: int) -> list[dict[str, Any]]:
        return (await self.get(f"/api/devices/{device_id}/ports")).get("ports", [])

    async def poe(self, device_id: int) -> list[dict[str, Any]]:
        return (await self.get(f"/api/metrics/device/{device_id}/poe")).get("ports", [])

    async def resources_latest(self) -> dict[str, dict[str, Any]]:
        """Latest CPU/memory per device; 404 on older managers."""
        return (await self.get("/api/metrics/resources/latest")).get("devices", {})

    async def interfaces_latest(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Latest interface counters per device; 404 on managers without the endpoint."""
        return (await self.get("/api/metrics/interfaces/latest")).get("devices", {})

    async def config_health(self, device_id: int) -> dict[str, Any]:
        return await self.get(f"/api/devices/{device_id}/config-health")

    async def insights(self) -> dict[str, Any]:
        """Fleet 'needs attention' list; 404/403 on older managers or narrow tokens."""
        return await self.get("/api/operations/insights")

    async def sites(self) -> list[dict[str, Any]]:
        data = await self.get("/api/sites")
        return data if isinstance(data, list) else data.get("sites", [])
