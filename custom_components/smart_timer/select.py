"""Select entity for new schedule action input."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartTimerCoordinator, signal_update


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([NewScheduleActionSelect(coordinator)])


class NewScheduleActionSelect(SelectEntity, RestoreEntity):
    """Action picker for creating a new schedule."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule_action"
    _attr_should_poll = False
    _attr_icon = "mdi:toggle-switch-outline"
    _attr_options = ["Turn On", "Turn Off"]

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_schedule_action"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"select.{coordinator.slug}_schedule_action"

    @property
    def current_option(self) -> str:
        action = self._coordinator.new_schedule_input.get("action", "turn_on")
        return "Turn On" if action == "turn_on" else "Turn Off"

    async def async_select_option(self, option: str) -> None:
        self._coordinator.new_schedule_input["action"] = "turn_on" if option == "Turn On" else "turn_off"
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state in self._attr_options:
            self._coordinator.new_schedule_input["action"] = "turn_on" if state.state == "Turn On" else "turn_off"

        @callback
        def _update() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
