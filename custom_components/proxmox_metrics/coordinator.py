"""HA polling adapter; no lifecycle calls during setup or polling."""
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ProxmoxClient, ProxmoxApiError, ProxmoxAuthError
from .const import (CONF_HOST, CONF_TOKEN_ID, CONF_TOKEN_SECRET, CONF_VERIFY_SSL,
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN)

_LOGGER = logging.getLogger(__name__)


class ProxmoxCoordinator(DataUpdateCoordinator):
    """Poll one endpoint; trigger reauthentication only for HTTP 401."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.client = ProxmoxClient(async_get_clientsession(hass), entry.data[CONF_HOST],
            entry.data[CONF_TOKEN_ID], entry.data[CONF_TOKEN_SECRET], entry.data.get(CONF_VERIFY_SSL, True))
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))

    async def _async_update_data(self):
        try:
            return await self.client.collect()
        except ProxmoxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from None
        except (ProxmoxApiError, ValueError, TypeError, KeyError) as err:
            raise UpdateFailed("Unable to collect Proxmox telemetry") from None
