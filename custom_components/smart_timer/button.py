"""Button entities for schedule management."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, parse_days
from .coordinator import SmartTimerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([
        AddScheduleButton(coordinator),
        RemoveLastScheduleButton(coordinator),
    ])


class AddScheduleButton(ButtonEntity):
    """Creates a new schedule from the current input values."""

    _attr_has_entity_name = True
    _attr_translation_key = "add_schedule"
    _attr_should_poll = False
    _attr_icon = "mdi:calendar-plus"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_add_schedule"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"button.{coordinator.slug}_add_schedule"

    async def async_press(self) -> None:
        inp = self._coordinator.new_schedule_input
        days = parse_days(inp.get("days", "Every Day"))
        await self._coordinator.async_add_schedule(
            action=inp.get("action", "turn_on"),
            time_str=inp.get("time", "08:00"),
            days=days,
            enabled=True,
        )
        _LOGGER.info(
            "Schedule added for %s: %s at %s (%s)",
            self._coordinator.entity_id,
            inp.get("action"),
            inp.get("time"),
            inp.get("days"),
        )


class RemoveLastScheduleButton(ButtonEntity):
    """Removes the most recently added schedule."""

    _attr_has_entity_name = True
    _attr_translation_key = "remove_last_schedule"
    _attr_should_poll = False
    _attr_icon = "mdi:calendar-minus"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_remove_last_schedule"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"button.{coordinator.slug}_remove_last_schedule"

    async def async_press(self) -> None:
        if self._coordinator.schedules:
            last = self._coordinator.schedules[-1]
            await self._coordinator.async_remove_schedule(last["id"])
            _LOGGER.info("Removed last schedule %s", last["id"])
