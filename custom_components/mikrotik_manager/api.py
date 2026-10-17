"""Thin read-only client for the MikroTik Manager REST API."""
from __future__ import annotations

from typing import Any

from aiohttp import ClientSession


class ManagerAuthError(Exception):
    """The token was rejected."""


class ManagerClient:
    def __init__(self, session: ClientSession, base_url: str, token: str, verify_ssl: bool) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._ssl = None if verify_ssl else False

    async def get(self, path: str) -> Any:
        async with self._session.get(
            f"{self._base}{path}", headers=self._headers, ssl=self._ssl, timeout=20
        ) as resp:
            if resp.status in (401, 403):
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
