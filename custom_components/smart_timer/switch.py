"""Dynamic switch entities — one per schedule, toggle on/off."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, format_days
from .coordinator import SmartTimerCoordinator, signal_update

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]

    # Per-schedule switches only (no master toggle)

    # Dynamic per-schedule switches
    tracked: dict[str, ScheduleSwitch] = {}
    key = f"sched_switches_{entry.entry_id}"
    hass.data[DOMAIN][key] = tracked

    def _sync_entities() -> None:
        sched_ids = {s["id"] for s in coordinator.schedules}
        _LOGGER.debug("Syncing schedule entities: %d schedules, %d tracked", len(sched_ids), len(tracked))

        # Add new
        new_entities = []
        for schedule in coordinator.schedules:
            if schedule["id"] not in tracked:
                entity = ScheduleSwitch(coordinator, schedule["id"])
                tracked[schedule["id"]] = entity
                new_entities.append(entity)
                _LOGGER.info("Adding schedule switch entity for %s", schedule["id"])
        if new_entities:
            async_add_entities(new_entities)

        # Remove deleted
        ent_reg = er.async_get(hass)
        for sid in list(tracked):
            if sid not in sched_ids:
                entity = tracked.pop(sid)
                _LOGGER.info("Removing schedule switch entity %s", sid)
                # Remove from entity registry so it fully disappears
                if entity.entity_id:
                    ent_reg.async_remove(entity.entity_id)
                else:
                    hass.async_create_task(entity.async_remove())

    @callback
    def _on_update() -> None:
        _sync_entities()

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_update(coordinator.entity_id), _on_update)
    )
    _sync_entities()


class ScheduleSwitch(SwitchEntity):
    """Toggle for a single schedule. Shows time/action/days in name."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: SmartTimerCoordinator, schedule_id: str) -> None:
        self._coordinator = coordinator
        self._schedule_id = schedule_id
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_sched_{schedule_id}"
        self._attr_device_info = coordinator.device_info

    @property
    def schedule_id(self) -> str:
        return self._schedule_id

    @property
    def name(self) -> str:
        s = self._get_schedule()
        if not s:
            return f"Schedule {self._schedule_id}"
        action = "ON" if s["action"] == "turn_on" else "OFF"
        days = format_days(s.get("days", []))
        return f"{action} at {s['time']} — {days}"

    @property
    def is_on(self) -> bool:
        s = self._get_schedule()
        return s.get("enabled", True) if s else False

    @property
    def extra_state_attributes(self) -> dict:
        s = self._get_schedule()
        if not s:
            return {}
        return {
            "schedule_id": s["id"],
            "action": s["action"],
            "time": s["time"],
            "days": format_days(s.get("days", [])),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_toggle_schedule(self._schedule_id, enabled=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_toggle_schedule(self._schedule_id, enabled=False)

    def _get_schedule(self) -> dict | None:
        for s in self._coordinator.schedules:
            if s["id"] == self._schedule_id:
                return s
        return None

    async def async_added_to_hass(self) -> None:
        @callback
        def _update() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
