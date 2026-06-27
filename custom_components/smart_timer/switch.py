from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import SmartTimerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([AwayModeSwitch(coordinator)])


class AwayModeSwitch(SwitchEntity, RestoreEntity):
    """Toggle away mode — random on/off within a time window to simulate presence."""

    _attr_has_entity_name = True
    _attr_translation_key = "away_mode"
    _attr_should_poll = False

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_away_mode"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"switch.{coordinator.slug}_away_mode"
        self._attr_is_on = False

    @property
    def icon(self) -> str:
        return "mdi:home-clock" if self.is_on else "mdi:home-clock-outline"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Sync from coordinator (loaded from storage)
        self._attr_is_on = self._coordinator.away_enabled
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        await self._coordinator.async_set_away_mode(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        await self._coordinator.async_set_away_mode(enabled=False)
