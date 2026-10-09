"""Explicit guest lifecycle controls. POST only inside async_press."""
from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from .api import ProxmoxApiError
from .controls import actions_for, can_press
from .const import CONF_ENABLE_CONTROLS
from .entity import ProxmoxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def discover():
        additions = []
        for resource, record in (coordinator.data or {}).get("guests", {}).items():
            for action in actions_for(record.get("kind")):
                key = (resource, action)
                if key not in seen:
                    seen.add(key)
                    additions.append(ProxmoxButton(coordinator, resource, action))
        if additions:
            async_add_entities(additions)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class ProxmoxButton(ProxmoxEntity, ButtonEntity):
    """HA button services do not provide built-in confirmation."""

    def __init__(self, coordinator, resource, action):
        super().__init__(coordinator, "guests", resource)
        self.action = action
        self._attr_unique_id = f"{self.entry_id}:guests:{resource}:{action}"
        self._attr_translation_key = action
        self._attr_icon = "mdi:power" if action == "start" else "mdi:restart"
        # A second intentional step is needed to expose destructive controls.
        self._attr_entity_registry_enabled_default = action not in {"stop", "reset"}

    @property
    def available(self):
        return (super().available
                and self.coordinator.entry.options.get(CONF_ENABLE_CONTROLS, False)
                and can_press(self.record, self.action))

    async def async_press(self):
        if not self.available:
            raise HomeAssistantError("Guest control disabled or unavailable in current state")
        try:
            # Read current node from coordinator: migrations don't strand buttons.
            await self.coordinator.client.control(self.record, self.action)
        except (ProxmoxApiError, ValueError, KeyError) as err:
            raise HomeAssistantError("Proxmox guest action failed; check token ACLs and task history") from None
        # Task acceptance isn't task completion. Subsequent polls show real state.
        await self.coordinator.async_request_refresh()
