import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector, entity_registry as er

from .const import CONF_ENTITY_ID, DOMAIN


class SmartTimerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            entity_id = user_input[CONF_ENTITY_ID]

            for entry in self._async_current_entries():
                if entry.data.get(CONF_ENTITY_ID) == entity_id:
                    return self.async_abort(reason="already_configured")

            readable = entity_id.split(".")[-1].replace("_", " ").title()
            return self.async_create_entry(
                title=readable,
                data={CONF_ENTITY_ID: entity_id},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        multiple=False,
                        filter=[
                            {"domain": "switch"},
                            {"domain": "light"},
                            {"domain": "fan"},
                            {"domain": "media_player"},
                            {"domain": "cover"},
                            {"domain": "climate"},
                            {"domain": "input_boolean"},
                            {"domain": "humidifier"},
                            {"domain": "siren"},
                            {"domain": "valve"},
                            {"domain": "vacuum"},
                        ],
                        exclude_entities=self._get_own_entities(),
                    )
                ),
            }),
        )

    def _get_own_entities(self) -> list[str]:
        ent_reg = er.async_get(self.hass)
        return [
            e.entity_id for e in ent_reg.entities.values()
            if e.platform == DOMAIN
        ]
