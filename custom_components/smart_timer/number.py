from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ACTION_TURN_OFF, ACTION_TURN_ON, DOMAIN
from .coordinator import SmartTimerCoordinator, signal_update


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([
        AutoOffNumber(coordinator),
        TurnOffInNumber(coordinator),
        TurnOnInNumber(coordinator),
    ])


class AutoOffNumber(NumberEntity, RestoreEntity):
    """Auto-off duration — device auto-turns-off every time it turns on."""

    _attr_has_entity_name = True
    _attr_translation_key = "auto_off"
    _attr_should_poll = False
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1440.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-cog"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_auto_off"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"number.{coordinator.slug}_auto_off"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            try:
                self._attr_native_value = float(state.state)
            except (ValueError, TypeError):
                self._attr_native_value = 0.0
        self._coordinator.number_entity = self
        self._coordinator.auto_off_minutes = self._attr_native_value
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._coordinator.number_entity is self:
            self._coordinator.number_entity = None

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = float(value)
        self._coordinator.auto_off_minutes = self._attr_native_value
        self.async_write_ha_state()


class TurnOffInNumber(NumberEntity):
    """Set minutes to start a turn-off timer. Resets to 0 when done."""

    _attr_has_entity_name = True
    _attr_translation_key = "turn_off_in"
    _attr_should_poll = False
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1440.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-off-outline"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_turn_off_in"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"number.{coordinator.slug}_turn_off_in"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        @callback
        def _update() -> None:
            if self._coordinator.timer_action != ACTION_TURN_OFF or self._coordinator.timer_expiry is None:
                if self._attr_native_value != 0.0:
                    self._attr_native_value = 0.0
                    self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = float(value)
        self.async_write_ha_state()
        if value > 0:
            await self._coordinator.async_start_timer(value, ACTION_TURN_OFF)
        else:
            if self._coordinator.timer_action == ACTION_TURN_OFF:
                await self._coordinator.async_cancel_timer()


class TurnOnInNumber(NumberEntity):
    """Set minutes to start a turn-on timer. Resets to 0 when done."""

    _attr_has_entity_name = True
    _attr_translation_key = "turn_on_in"
    _attr_should_poll = False
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1440.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-play-outline"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_turn_on_in"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"number.{coordinator.slug}_turn_on_in"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        @callback
        def _update() -> None:
            if self._coordinator.timer_action != ACTION_TURN_ON or self._coordinator.timer_expiry is None:
                if self._attr_native_value != 0.0:
                    self._attr_native_value = 0.0
                    self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = float(value)
        self.async_write_ha_state()
        if value > 0:
            await self._coordinator.async_start_timer(value, ACTION_TURN_ON)
        else:
            if self._coordinator.timer_action == ACTION_TURN_ON:
                await self._coordinator.async_cancel_timer()
