from __future__ import annotations

from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import SmartTimerCoordinator, signal_update

_REFRESH_INTERVAL = timedelta(seconds=15)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([TimerActiveSensor(coordinator)])


class TimerActiveSensor(BinarySensorEntity):
    """ON while a countdown timer is running."""

    _attr_has_entity_name = True
    _attr_translation_key = "timer_active"
    _attr_should_poll = False

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_timer_active"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"binary_sensor.{coordinator.slug}_timer_active"
        self._unsub_interval = None

    @property
    def is_on(self) -> bool:
        return self._coordinator.timer_expiry is not None

    @property
    def icon(self) -> str:
        return "mdi:timer-play" if self.is_on else "mdi:timer-outline"

    @property
    def extra_state_attributes(self) -> dict:
        expiry = self._coordinator.timer_expiry
        action = self._coordinator.timer_action
        if not expiry:
            return {"expiry": None, "remaining": "0s", "action": None}
        diff = expiry - dt_util.now()
        secs = max(0, int(diff.total_seconds()))
        mins = secs // 60
        s = secs % 60
        if mins > 0:
            remaining = f"{mins}m {s}s"
        else:
            remaining = f"{s}s"
        return {
            "expiry": expiry.isoformat(),
            "remaining": remaining,
            "action": action,
        }

    async def async_added_to_hass(self) -> None:
        def _start_interval() -> None:
            if self._unsub_interval is None:
                self._unsub_interval = async_track_time_interval(
                    self.hass, self._tick, _REFRESH_INTERVAL
                )

        def _stop_interval() -> None:
            if self._unsub_interval is not None:
                self._unsub_interval()
                self._unsub_interval = None

        @callback
        def _update() -> None:
            self.async_write_ha_state()
            if self.is_on:
                _start_interval()
            else:
                _stop_interval()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
        self.async_on_remove(_stop_interval)
        if self.is_on:
            _start_interval()

    @callback
    def _tick(self, now: datetime) -> None:
        self.async_write_ha_state()
