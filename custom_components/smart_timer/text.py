"""Text entities for new schedule time and days input."""
from __future__ import annotations

import re

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartTimerCoordinator, signal_update

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([
        NewScheduleTimeText(coordinator),
        NewScheduleDaysText(coordinator),
    ])


class NewScheduleTimeText(TextEntity, RestoreEntity):
    """Time input for creating a new schedule (HH:MM)."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule_time"
    _attr_should_poll = False
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_schedule_time"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"text.{coordinator.slug}_schedule_time"

    @property
    def native_value(self) -> str:
        return self._coordinator.new_schedule_input.get("time", "08:00")

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        match = _TIME_RE.match(value)
        if not match:
            return
        normalized = f"{int(match.group(1)):02d}:{match.group(2)}"
        self._coordinator.new_schedule_input["time"] = normalized
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and _TIME_RE.match(state.state or ""):
            self._coordinator.new_schedule_input["time"] = state.state

        @callback
        def _update() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )


class NewScheduleDaysText(TextEntity, RestoreEntity):
    """Days input for creating a new schedule. Type: Mon,Tue,Fri or Every Day."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule_days"
    _attr_should_poll = False
    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_schedule_days"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"text.{coordinator.slug}_schedule_days"

    @property
    def native_value(self) -> str:
        return self._coordinator.new_schedule_input.get("days", "Every Day")

    async def async_set_value(self, value: str) -> None:
        self._coordinator.new_schedule_input["days"] = value.strip()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state:
            self._coordinator.new_schedule_input["days"] = state.state

        @callback
        def _update() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
