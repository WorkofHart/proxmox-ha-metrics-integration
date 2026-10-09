"""Recorder-compatible telemetry with incremental entity discovery."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.core import callback
from .entity import ProxmoxEntity
from .metrics import new_sensor_keys, sensor_value

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def discover():
        additions = new_sensor_keys(coordinator.data or {}, seen)
        if additions:
            async_add_entities(ProxmoxSensor(coordinator, group, resource, metric)
                               for group, resource, metric in additions)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class ProxmoxSensor(ProxmoxEntity, SensorEntity):
    """A scalar metric; missing fields are unavailable, never stale values."""

    def __init__(self, coordinator, group, resource, metric):
        super().__init__(coordinator, group, resource)
        self.metric = metric
        self._attr_unique_id = f"{self.entry_id}:{group}:{resource}:{metric.key}"
        self._attr_translation_key = metric.key.replace(".", "_")
        self._attr_native_unit_of_measurement = metric.unit
        self._attr_device_class = SensorDeviceClass(metric.device_class) if metric.device_class else None
        self._attr_state_class = SensorStateClass(metric.state_class) if metric.state_class else None
        if metric.state_class:
            self._attr_suggested_display_precision = 2 if metric.unit == "%" else 0

    @property
    def available(self):
        # Status is useful even for an offline node/inactive datastore.
        healthy = self.coordinator.last_update_success and bool(self.record)
        if self.metric.key != "status":
            healthy = healthy and super().available
        return healthy and self.native_value is not None

    @property
    def native_value(self):
        return sensor_value(self.record, self.metric)
