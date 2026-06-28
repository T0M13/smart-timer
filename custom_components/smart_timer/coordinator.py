from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time, async_track_time_change

from .const import ACTION_TURN_OFF, ACTION_TURN_ON, DOMAIN

_LOGGER = logging.getLogger(__name__)

_INACTIVE_STATES = frozenset({
    STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN,
    "closed", "closing", "idle", "docked", "standby",
})

RECOVERY_GRACE_SECONDS = 15


def signal_update(entity_id: str) -> str:
    return f"{DOMAIN}_update_{entity_id}"


def _is_active(state_obj) -> bool:
    return bool(state_obj and state_obj.state not in _INACTIVE_STATES)


async def _execute_action(hass: HomeAssistant, entity_id: str, action: str) -> None:
    domain = entity_id.split(".")[0]
    if action == ACTION_TURN_ON:
        if domain == "cover":
            await hass.services.async_call("cover", "open_cover", {"entity_id": entity_id}, context=Context())
        else:
            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": entity_id}, context=Context())
    else:
        if domain == "cover":
            await hass.services.async_call("cover", "close_cover", {"entity_id": entity_id}, context=Context())
        elif domain == "vacuum":
            await hass.services.async_call("vacuum", "return_to_base", {"entity_id": entity_id}, context=Context())
        else:
            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": entity_id}, context=Context())


class SmartTimerCoordinator:
    """Manages timers and schedules for one device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entity_id: str) -> None:
        self.hass = hass
        self.entry = entry
        self.entity_id = entity_id
        self.slug = entity_id.split(".")[-1]

        self.device_info: DeviceInfo | None = None

        self.is_recovering = True
        self.recover_task: asyncio.Task | None = None

        # Timer
        self.timer_action: str | None = None
        self.timer_expiry: datetime | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None

        # Auto-off
        self.auto_off_minutes: float = 0.0
        self.number_entity = None

        # Schedules (service-based, multi)
        self.schedules: list[dict] = []
        self._unsub_schedules: list[CALLBACK_TYPE] = []

        # Selected schedule for removal via dropdown
        self.selected_schedule_to_remove: str | None = None

        # Input state for creating new schedules via entities
        self.new_schedule_input: dict = {
            "action": "turn_on",
            "time": "08:00",
            "days": "Every Day",
        }

    async def async_setup(self) -> None:
        self._link_device()
        await self._async_load()

    def _link_device(self) -> None:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        target = ent_reg.async_get(self.entity_id)
        if target and target.device_id:
            phys = dev_reg.async_get(target.device_id)
            if phys:
                self.device_info = DeviceInfo(identifiers=phys.identifiers)
                return
        readable = self.slug.replace("_", " ").title()
        ids = {(DOMAIN, self.entry.entry_id)}
        dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers=ids,
            name=readable,
        )
        self.device_info = DeviceInfo(identifiers=ids, name=readable)

    async def async_unload(self) -> None:
        if self.recover_task:
            self.recover_task.cancel()
            self.recover_task = None
        self._cancel_timer()
        self._cancel_schedules()
        await self._async_save()

    @callback
    def handle_shutdown(self, event: Event) -> None:
        self._cancel_timer()
        self._cancel_schedules()

    # ---- Timer ----

    async def async_start_timer(self, minutes: float, action: str = ACTION_TURN_OFF) -> None:
        self._cancel_timer()
        if minutes <= 0:
            await self._async_clear_timer()
            return
        self.timer_action = action
        self.timer_expiry = dt_util.now() + timedelta(minutes=minutes)
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_timer_expired, self.timer_expiry
        )
        self._notify_update()
        await self._async_save()

    async def async_start_timer_from_expiry(self, expiry_iso: str, action: str) -> None:
        expiry = dt_util.parse_datetime(expiry_iso)
        if not expiry or expiry <= dt_util.now():
            await self._async_clear_timer()
            return
        self._cancel_timer()
        self.timer_action = action
        self.timer_expiry = expiry
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_timer_expired, self.timer_expiry
        )
        self._notify_update()

    async def async_cancel_timer(self) -> None:
        await self._async_clear_timer()
        await self._async_save()

    async def _async_timer_expired(self, now: datetime) -> None:
        self._unsub_timer = None
        action = self.timer_action or ACTION_TURN_OFF
        entity_id = self.entity_id
        self.timer_action = None
        self.timer_expiry = None
        self._notify_update()
        await self._async_save()
        await _execute_action(self.hass, entity_id, action)
        self.hass.bus.async_fire("smart_timer_expired", {
            "entity_id": entity_id,
            "action": action,
        })

    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _async_clear_timer(self) -> None:
        self._cancel_timer()
        self.timer_action = None
        self.timer_expiry = None
        self._notify_update()

    # ---- Auto-off ----

    @property
    def auto_off_value(self) -> float:
        if self.number_entity and self.number_entity.hass:
            return float(self.number_entity.native_value or 0.0)
        return self.auto_off_minutes

    async def async_handle_state_change(self, event: Event) -> None:
        if self.is_recovering:
            return
        new_s = event.data.get("new_state")
        old_s = event.data.get("old_state")
        if new_s and old_s and new_s.state == old_s.state:
            return

        was_active = _is_active(old_s)
        now_active = _is_active(new_s)

        if now_active and not was_active:
            auto_off = self.auto_off_value
            if auto_off > 0 and self.timer_expiry is None:
                await self.async_start_timer(auto_off, ACTION_TURN_OFF)
        elif was_active and not now_active:
            if self._unsub_timer:
                await self._async_clear_timer()
                await self._async_save()

    # ---- Schedules ----

    async def async_add_schedule(
        self, action: str, time_str: str, days: list[int] | None = None, enabled: bool = True
    ) -> str:
        schedule_id = uuid.uuid4().hex[:8]
        schedule = {
            "id": schedule_id,
            "action": action,
            "time": time_str,
            "days": days or [],
            "enabled": enabled,
        }
        self.schedules.append(schedule)
        self._setup_single_schedule(schedule)
        await self._async_save()
        self._notify_update()
        return schedule_id

    async def async_toggle_schedule(self, schedule_id: str, enabled: bool | None = None) -> bool:
        for s in self.schedules:
            if s["id"] == schedule_id:
                s["enabled"] = not s.get("enabled", True) if enabled is None else enabled
                self._cancel_schedules()
                self._setup_all_schedules()
                await self._async_save()
                self._notify_update()
                return True
        return False

    async def async_remove_schedule(self, schedule_id: str) -> bool:
        found = None
        for i, s in enumerate(self.schedules):
            if s["id"] == schedule_id:
                found = i
                break
        if found is None:
            return False
        self.schedules.pop(found)
        self._cancel_schedules()
        self._setup_all_schedules()
        await self._async_save()
        self._notify_update()
        return True

    def _setup_all_schedules(self) -> None:
        for s in self.schedules:
            if s.get("enabled", True):
                self._setup_single_schedule(s)

    def _setup_single_schedule(self, schedule: dict) -> None:
        parts = schedule["time"].split(":")
        if len(parts) != 2:
            return
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            return

        @callback
        def _fire(now: datetime, sched=schedule) -> None:
            if sched.get("days"):
                today = now.weekday()
                if today not in [int(d) for d in sched["days"]]:
                    return
            self.hass.async_create_task(
                _execute_action(self.hass, self.entity_id, sched["action"])
            )
            self.hass.bus.async_fire("smart_timer_schedule_fired", {
                "entity_id": self.entity_id,
                "schedule_id": sched["id"],
                "action": sched["action"],
            })

        unsub = async_track_time_change(self.hass, _fire, hour=hour, minute=minute, second=0)
        self._unsub_schedules.append(unsub)

    def _cancel_schedules(self) -> None:
        for unsub in self._unsub_schedules:
            unsub()
        self._unsub_schedules.clear()

    def get_next_schedule_time(self) -> datetime | None:
        if not self.schedules:
            return None
        now = dt_util.now()
        earliest = None
        for s in self.schedules:
            if not s.get("enabled", True):
                continue
            parts = s["time"].split(":")
            if len(parts) != 2:
                continue
            try:
                hour, minute = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            if s.get("days"):
                int_days = [int(d) for d in s["days"]]
                for _ in range(8):
                    if candidate.weekday() in int_days:
                        break
                    candidate += timedelta(days=1)
                else:
                    continue
            if earliest is None or candidate < earliest:
                earliest = candidate
        return earliest

    # ---- Persistence ----

    async def _async_load(self) -> None:
        store = self.hass.data[DOMAIN]["store"]
        raw = await store.async_load() or {}
        data = raw.get("devices", {}).get(self.entity_id, {})
        if not data:
            return
        timer = data.get("timer")
        if timer and timer.get("expiry"):
            self.timer_action = timer.get("action", ACTION_TURN_OFF)
        self.schedules = data.get("schedules", [])

    async def _async_save(self) -> None:
        if self.hass.is_stopping:
            return
        async with self.hass.data[DOMAIN]["save_lock"]:
            store = self.hass.data[DOMAIN]["store"]
            raw = await store.async_load() or {}
            devices = raw.get("devices", {})
            devices[self.entity_id] = {
                "timer": {
                    "action": self.timer_action,
                    "expiry": self.timer_expiry.isoformat() if self.timer_expiry else None,
                } if self.timer_expiry else None,
                "schedules": self.schedules,
            }
            raw["devices"] = devices
            await store.async_save(raw)

    # ---- Recovery ----

    async def async_recover(self) -> None:
        try:
            store = self.hass.data[DOMAIN]["store"]
            raw = await store.async_load() or {}
            data = raw.get("devices", {}).get(self.entity_id, {})
            timer = data.get("timer")

            if timer and timer.get("expiry"):
                await asyncio.sleep(RECOVERY_GRACE_SECONDS)
                expiry_str = timer["expiry"]
                action = timer.get("action", ACTION_TURN_OFF)
                expiry = dt_util.parse_datetime(expiry_str)
                if expiry and expiry > dt_util.now():
                    await self.async_start_timer_from_expiry(expiry_str, action)
                else:
                    state = self.hass.states.get(self.entity_id)
                    if expiry and _is_active(state) and action == ACTION_TURN_OFF:
                        await _execute_action(self.hass, self.entity_id, action)
                    await self._async_clear_timer()
                    await self._async_save()

            self._setup_all_schedules()
        finally:
            self.is_recovering = False

    def _notify_update(self) -> None:
        async_dispatcher_send(self.hass, signal_update(self.entity_id))
