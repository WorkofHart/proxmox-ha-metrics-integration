"""Runnable pure-Python validation for the Proxmox transport layer."""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "proxmox_metrics"
package = types.ModuleType("proxmox_metrics")
package.__path__ = [str(PACKAGE_DIR)]
sys.modules.setdefault("proxmox_metrics", package)
api = importlib.import_module("proxmox_metrics.api")


class ProxmoxApiTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        return api.ProxmoxClient(object(), "pve.example:8006", "ha@pve!metrics", "secret")

    async def test_collect_preserves_qemu_and_lxc_source_kind(self):
        client = self.make_client()
        responses = {
            "nodes": [{"node": "pve-a", "status": "online"}],
            "nodes/pve-a/status": {"cpu": 0.25, "memory": {"used": 10, "total": 20}, "cpuinfo": {"cpus": 8, "model": "Test CPU"}},
            "nodes/pve-a/qemu": [{"vmid": 100, "name": "web", "status": "running"}],
            "nodes/pve-a/lxc": [{"vmid": 200, "name": "dns", "status": "running"}],
            "nodes/pve-a/storage": [{"storage": "local", "active": 1, "used": 50, "total": 100}],
            "nodes/pve-a/rrddata?timeframe=hour&cf=AVERAGE": [],
            "nodes/pve-a/qemu/100/status/current": {"cpu": 0.5, "mem": 10, "maxmem": 20},
            "nodes/pve-a/lxc/200/status/current": {"cpu": 0.75, "mem": 15, "maxmem": 20},
        }

        async def request(path, method="GET"):
            self.assertEqual(method, "GET")
            return responses[path]

        client.request = AsyncMock(side_effect=request)
        data = await client.collect()
        self.assertEqual(data["guests"]["qemu:100"]["kind"], "qemu")
        self.assertEqual(data["guests"]["lxc:200"]["kind"], "lxc")
        self.assertEqual(data["nodes"]["pve-a"]["cpu_count"], 8)
        self.assertEqual(data["nodes"]["pve-a"]["memory_percent"], 50)
        paths = [call.args[0] for call in client.request.call_args_list]
        self.assertIn("nodes/pve-a/qemu/100/status/current", paths)
        self.assertIn("nodes/pve-a/lxc/200/status/current", paths)

    async def test_lifecycle_paths_and_controls_are_type_safe(self):
        self.assertEqual(api.guest_path({"node": "pve-a", "kind": "qemu", "vmid": 100}, "reset"), "nodes/pve-a/qemu/100/status/reset")
        self.assertEqual(api.guest_path({"node": "pve-a", "kind": "lxc", "vmid": 200}, "reboot"), "nodes/pve-a/lxc/200/status/reboot")
        with self.assertRaises(ValueError):
            api.guest_path({"node": "pve-a", "kind": "lxc", "vmid": 200}, "reset")
        client = self.make_client()
        client.request = AsyncMock(return_value="UPID:pve-a:0001")
        self.assertTrue((await client.control({"node": "pve-a", "kind": "qemu", "vmid": 100}, "start")).startswith("UPID:"))
        client.request.assert_awaited_once_with("nodes/pve-a/qemu/100/status/start", "POST")

    def test_endpoint_validation_and_normalization(self):
        self.assertEqual(api.normalize_endpoint("PVE.EXAMPLE"), "https://pve.example:8006")
        for bad in ("http://pve.example", "https://user@pve.example", "https://pve.example/api2/json"):
            with self.assertRaises(ValueError):
                api.normalize_endpoint(bad)


if __name__ == "__main__":
    unittest.main()
