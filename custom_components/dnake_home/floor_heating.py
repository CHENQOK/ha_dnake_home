import logging
from homeassistant.const import UnitOfTemperature
from homeassistant.components.climate import ClimateEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
)

from .core.assistant import assistant
from .core.constant import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

_hvac_table = {
    HVACMode.OFF: 0,
    HVACMode.HEAT: 1,
}

_min_temperature = 16

_max_temperature = 32


def load_floor_heatings(device_list):
    climates = [
        DnakeFloorHeating(device) for device in device_list if device.get("devType") == 2048
    ]
    _LOGGER.info(f"find floor heating num: {len(climates)}")
    assistant.entries["floor_heating"] = climates


def update_floor_heatings_state(states):
    floor_heatings = assistant.entries["floor_heating"]
    for floor_heating in floor_heatings:
        state = next((state for state in states if floor_heating.is_hint_state(state)), None)
        if state:
            floor_heating.update_state(state)



class DnakeFloorHeating(ClimateEntity):

    def __init__(self, device):
        self._name = device.get("devName")
        gateway_info = device.get("gatewayDeviceInfo", {})
        self._dev_no = gateway_info.get("devNo")
        self._dev_ch = gateway_info.get("devCh")
        self._target_temperature = _min_temperature
        self._current_temperature = _min_temperature
        self._hvac_mode = HVACMode.OFF

    def is_hint_state(self, state):
        return state.get("devNo") == self._dev_no and state.get("devCh") == self._dev_ch

    @property
    def unique_id(self):
        return f"dnake_floor_heating_{self._dev_ch}_{self._dev_no}"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"floor_heating_{self._dev_ch}_{self._dev_no}")},
            name=self._name,
            manufacturer=MANUFACTURER,
            model="地暖控制",
            via_device=(DOMAIN, "gateway"),
        )

    @property
    def should_poll(self):
        return False

    @property
    def name(self):
        return self._name

    @property
    def target_temperature(self):
        return self._target_temperature

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def min_temp(self):
        return _min_temperature

    @property
    def max_temp(self):
        return _max_temperature

    @property
    def target_temperature_step(self):
        return 1

    @property
    def hvac_mode(self):
        return self._hvac_mode

    @property
    def hvac_modes(self):
        return list(_hvac_table.keys())


    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def supported_features(self):
        return ClimateEntityFeature.TARGET_TEMPERATURE

    async def _async_turn_to(self, is_open: bool):
        return await self.hass.async_add_executor_job(
            assistant.set_floor_heating_power,
            self._dev_no,
            self._dev_ch,
            is_open,
        )

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        is_success = await self.hass.async_add_executor_job(
            assistant.set_floor_heating_temperature,
            self._dev_no,
            self._dev_ch,
            temperature,
        )
        if is_success:
            self._target_temperature = temperature
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            close_success = await self._async_turn_to(False)
            if close_success:
                self._hvac_mode = HVACMode.OFF
                self.async_write_ha_state()
        else:
            # 地暖开启后默认为加热模式
            open_success = await self._async_turn_to(True)
            if open_success:
                self._hvac_mode = HVACMode.HEAT
                self.async_write_ha_state()


    def update_state(self, state):
        self._target_temperature = state.get("reports", {}).get("temp", _min_temperature)/100
        self._current_temperature = state.get("reports", {}).get("tempIndoor", _min_temperature)/100
        if state.get("reports", {}).get("powerOn", 0) == 0:
            self._hvac_mode = HVACMode.OFF
        else:
            self._hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()
