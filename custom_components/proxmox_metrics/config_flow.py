"""UI setup, token reauthentication, endpoint reconfiguration and options."""
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import ProxmoxClient, ProxmoxApiError, ProxmoxAuthError, ProxmoxPermissionError, normalize_endpoint
from .const import (DOMAIN, CONF_HOST, CONF_TOKEN_ID, CONF_TOKEN_SECRET, CONF_VERIFY_SSL,
                    CONF_SCAN_INTERVAL, CONF_ENABLE_CONTROLS, DEFAULT_SCAN_INTERVAL)


def schema(defaults, include_host=True):
    fields = {}
    if include_host:
        fields[vol.Required("name", default=defaults.get("name", "Proxmox"))] = str
        fields[vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, ""))] = str
    fields[vol.Required(CONF_TOKEN_ID, default=defaults.get(CONF_TOKEN_ID, ""))] = str
    # Never repopulate or expose the stored secret in the UI.
    fields[vol.Required(CONF_TOKEN_SECRET)] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    fields[vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True))] = bool
    return vol.Schema(fields)


class ProxmoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per cluster endpoint; multiple independent entries supported."""
    VERSION = 1

    async def _validate(self, data):
        try:
            data[CONF_HOST] = normalize_endpoint(data[CONF_HOST])
            client = ProxmoxClient(async_get_clientsession(self.hass), data[CONF_HOST],
                data[CONF_TOKEN_ID], data[CONF_TOKEN_SECRET], data[CONF_VERIFY_SSL])
            await client.validate()
            inventory = await client.collect()
            if not any(n.get("available") for n in inventory["nodes"].values()):
                return "no_accessible_nodes"
        except ProxmoxAuthError:
            return "invalid_auth"
        except ProxmoxPermissionError:
            return "insufficient_permissions"
        except ValueError:
            return "invalid_input"
        except ProxmoxApiError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = dict(user_input)
            error = await self._validate(data)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(data[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data["name"], data=data)
        return self.async_show_form(step_id="user", data_schema=schema(user_input or {}), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            error = await self._validate(data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema(entry.data, False), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            error = await self._validate(data)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(data[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(entry, data_updates=data,
                    unique_id=data[CONF_HOST], title=data["name"], reason="reconfigure_successful")
        return self.async_show_form(step_id="reconfigure", data_schema=schema(entry.data), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ProxmoxOptionsFlow()


class ProxmoxOptionsFlow(OptionsFlow):
    """Read-only by default; lifecycle controls require explicit enablement."""
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=15, max=900)),
            vol.Required(CONF_ENABLE_CONTROLS, default=self.config_entry.options.get(
                CONF_ENABLE_CONTROLS, False)): bool,
        }))
