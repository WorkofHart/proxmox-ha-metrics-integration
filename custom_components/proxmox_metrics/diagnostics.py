"""Secret-safe diagnostics: normalized allowlisted fields only."""
from .redaction import diagnostics_payload


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return diagnostics_payload(entry.data, entry.options, coordinator.data,
                               coordinator.last_update_success)
