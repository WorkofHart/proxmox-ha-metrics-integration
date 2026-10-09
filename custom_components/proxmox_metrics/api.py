"""Async Proxmox transport and collection, independent of Home Assistant."""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp
from .metrics import normalize


class ProxmoxApiError(Exception):
    """Sanitized transport, permission, or response error."""


class ProxmoxAuthError(ProxmoxApiError):
    """Token authentication rejected (HTTP 401)."""


class ProxmoxPermissionError(ProxmoxApiError):
    """Effective ACL denies operation (HTTP 403)."""


def normalize_endpoint(value: str) -> str:
    """Require HTTPS; reject credentials, paths, queries and fragments."""
    value = value.strip().rstrip("/")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.path or parts.query or parts.fragment):
        raise ValueError("Use an HTTPS origin without credentials or a path")
    port = parts.port or 8006
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return f"https://{host}:{port}"


def guest_path(guest: dict, action: str) -> str:
    """Route only by preserved source kind: both guest types have vmid."""
    kind = guest["kind"]
    allowed = {"start", "shutdown", "stop", "reboot"}
    if kind == "qemu":
        allowed.add("reset")
    if kind not in {"qemu", "lxc"} or action not in allowed:
        raise ValueError("Unsupported guest lifecycle action")
    vmid = int(guest["vmid"])
    if vmid <= 0:
        raise ValueError("Invalid guest ID")
    return f"nodes/{quote(guest['node'], safe='')}/{kind}/{vmid}/status/{action}"


class ProxmoxClient:
    """Shared aiohttp session, bounded concurrency, per-request timeout."""

    def __init__(self, session: aiohttp.ClientSession, host: str, token_id: str,
                 token_secret: str, verify_ssl: bool = True) -> None:
        self.session = session
        self.base_url = normalize_endpoint(host)
        if "!" not in token_id or "@" not in token_id or any(c in token_id + token_secret for c in "\r\n"):
            raise ValueError("Invalid API token format")
        if not token_secret:
            raise ValueError("API token secret is required")
        self._authorization = f"PVEAPIToken={token_id}={token_secret}"
        self.verify_ssl = verify_ssl
        self._semaphore = asyncio.Semaphore(6)
        self._control_locks: dict[str, asyncio.Lock] = {}

    async def request(self, path: str, method: str = "GET") -> Any:
        """No redirects or retries: never leak auth or repeat a POST."""
        async with self._semaphore:
            try:
                async with self.session.request(
                    method, f"{self.base_url}/api2/json/{path}",
                    headers={"Authorization": self._authorization},
                    ssl=None if self.verify_ssl else False,
                    timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False,
                ) as response:
                    if response.status == 401:
                        raise ProxmoxAuthError("Proxmox rejected API token")
                    if response.status == 403:
                        raise ProxmoxPermissionError("Proxmox denied permission")
                    if response.status != 200:
                        raise ProxmoxApiError(f"Proxmox returned HTTP {response.status}")
                    body = await response.json(content_type=None)
                    if not isinstance(body, dict) or "data" not in body:
                        raise ProxmoxApiError("Invalid Proxmox response envelope")
                    return body["data"]
            except (aiohttp.ClientError, TimeoutError, ValueError):
                raise ProxmoxApiError("Proxmox connection or JSON response failed") from None

    async def validate(self) -> str:
        data = await self.request("version")
        if not isinstance(data, dict) or not data.get("version"):
            raise ProxmoxApiError("Invalid version response")
        return str(data["version"])

    async def control(self, guest: dict, action: str) -> str:
        path = guest_path(guest, action)
        key = f"{guest['kind']}:{guest['vmid']}"
        async with self._control_locks.setdefault(key, asyncio.Lock()):
            task = await self.request(path, "POST")
        if not isinstance(task, str) or not task.startswith("UPID:"):
            raise ProxmoxApiError("No task ID returned; do not retry blindly")
        return task

    async def _optional(self, path: str) -> Any:
        try:
            return await self.request(path)
        except ProxmoxAuthError:
            raise
        except ProxmoxApiError:
            return None

    async def collect(self) -> dict[str, dict]:
        """Inventory each poll; isolate resource errors from healthy peers."""
        nodes = await self.request("nodes")
        if not isinstance(nodes, list):
            raise ProxmoxApiError("Invalid node inventory")
        result: dict[str, dict] = {"nodes": {}, "guests": {}, "storage": {}}

        async def collect_guest(node: str, kind: str, guest: dict) -> None:
            if guest.get("vmid") is None:
                return
            vmid = int(guest["vmid"])
            current = await self._optional(f"nodes/{quote(node, safe='')}/{kind}/{vmid}/status/current")
            values = {**guest, **(current if isinstance(current, dict) else {})}
            values.update(node=node, kind=kind, vmid=vmid, available=isinstance(current, dict))
            result["guests"][f"{kind}:{vmid}"] = normalize(values, kind)

        async def collect_node(record: dict) -> None:
            node = record.get("node")
            if not isinstance(node, str):
                return
            base = f"nodes/{quote(node, safe='')}"
            status = await self._optional(f"{base}/status")
            values = {**record, **(status if isinstance(status, dict) else {})}
            values.update(available=isinstance(status, dict), kind="node", node=node)
            result["nodes"][node] = normalize(values, "node")
            if record.get("status") == "offline":
                result["nodes"][node]["available"] = False
                return
            qemu, lxc, storage, rrd = await asyncio.gather(
                self._optional(f"{base}/qemu"), self._optional(f"{base}/lxc"),
                self._optional(f"{base}/storage"),
                self._optional(f"{base}/rrddata?timeframe=hour&cf=AVERAGE"),
            )
            if isinstance(rrd, list):
                fresh = [r for r in rrd if isinstance(r, dict)
                         and isinstance(r.get("time"), (int, float))
                         and 0 <= time.time() - r["time"] <= 180
                         and any(r.get(k) is not None for k in ("netin", "netout", "iowait"))]
                if fresh:
                    last = max(fresh, key=lambda r: r["time"])
                    for source, target in (("netin", "network_in_rate"), ("netout", "network_out_rate"),
                                           ("iowait", "iowait")):
                        if last.get(source) is not None:
                            result["nodes"][node][target] = last[source]
            if isinstance(storage, list):
                for item in storage:
                    if not isinstance(item, dict) or not item.get("storage"):
                        continue
                    key = f"{node}:{item['storage']}"
                    result["storage"][key] = normalize({**item, "node": node, "kind": "storage",
                        "available": bool(item.get("active", 0))}, "storage")
            # vmid is present in BOTH inventories; preserve the source endpoint.
            await asyncio.gather(*(collect_guest(node, kind, guest)
                for kind, inventory in (("qemu", qemu), ("lxc", lxc))
                if isinstance(inventory, list) for guest in inventory if isinstance(guest, dict)))

        await asyncio.gather(*(collect_node(node) for node in nodes if isinstance(node, dict)))
        return result
