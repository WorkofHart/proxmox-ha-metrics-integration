"""Shared resource identity and availability."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class ProxmoxEntity(CoordinatorEntity):
    """Endpoint-scoped identity avoids collisions across independent clusters."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, group, resource):
        super().__init__(coordinator)
        self.group = group
        self.resource = resource
        self.entry_id = coordinator.entry.entry_id

    @property
    def record(self):
        return (self.coordinator.data or {}).get(self.group, {}).get(self.resource, {})

    @property
    def available(self):
        return super().available and bool(self.record.get("available"))

    @property
    def device_info(self):
        record = self.record
        kind = record.get("kind", "node")
        name = record.get("name") or record.get("storage") or record.get("node") or self.resource
        if kind in {"qemu", "lxc"}:
            name = f"{kind.upper()} {record.get('vmid')} {name}"
        info = DeviceInfo(identifiers={(DOMAIN, f"{self.entry_id}:{self.group}:{self.resource}")},
            name=f"{self.coordinator.entry.title} {name}", manufacturer="Proxmox",
            model={"node": "VE node", "qemu": "QEMU VM", "lxc": "LXC container",
                   "storage": "Storage"}.get(kind, kind))
        if self.group != "nodes" and record.get("node"):
            info["via_device"] = (DOMAIN, f"{self.entry_id}:nodes:{record['node']}")
        return info
