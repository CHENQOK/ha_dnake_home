import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .core.assistant import assistant
from .core.constant import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

SPEED_LIST = ["low", "medium", "high"]
SPEED_MAP = {"low": 1, "medium": 2, "high": 3}


def load_air_fresh_devices(device_list):
    air_fresh_devices = [
        DnakeAirFresh(device) for device in device_list if device.get("devType") == 1792
    ]
    _LOGGER.info(f"find air fresh num: {len(air_fresh_devices)}")
    assistant.entries["air_fresh"] = air_fresh_devices


def update_air_fresh_state(states):
    air_fresh_devices = assistant.entries.get("air_fresh", [])
    for device in air_fresh_devices:
        state = next((state for state in states if device.is_hint_state(state)), None)
        if state:
            device.update_state(state)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    air_fresh_list = assistant.entries.get("air_fresh", [])
    if air_fresh_list:
        async_add_entities(air_fresh_list)


class DnakeAirFresh(FanEntity):

    def __init__(self, device):
        self._name = device.get("devName")
        gateway_info = device.get("gatewayDeviceInfo", {})
        self._dev_no = gateway_info.get("devNo")
        self._dev_ch = gateway_info.get("devCh")
        self._is_on = False
        self._percentage = 0

    def is_hint_state(self, state):
        return state.get("devNo") == self._dev_no and state.get("devCh") == self._dev_ch

    @property
    def unique_id(self):
        return f"dnake_air_fresh_{self._dev_ch}_{self._dev_no}"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"air_fresh_{self._dev_ch}_{self._dev_no}")},
            name=self._name,
            manufacturer=MANUFACTURER,
            model="新风系统",
            via_device=(DOMAIN, "gateway"),
        )

    @property
    def should_poll(self):
        return False

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._is_on

    @property
    def percentage(self):
        return self._percentage

    @property
    def speed_count(self):
        return len(SPEED_LIST)

    @property
    def supported_features(self):
        return FanEntityFeature.SET_SPEED

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if percentage is not None:
            speed = percentage_to_ordered_list_item(SPEED_LIST, percentage)
            wind_speed = SPEED_MAP[speed]
            is_success = await self.hass.async_add_executor_job(
                assistant.set_air_fresh_wind_speed,
                self._dev_no,
                self._dev_ch,
                wind_speed,
            )
            if is_success:
                self._percentage = percentage
                self._is_on = True
                self.async_write_ha_state()
        else:
            is_success = await self.hass.async_add_executor_job(
                assistant.set_air_fresh_power,
                self._dev_no,
                self._dev_ch,
                True,
            )
            if is_success:
                self._is_on = True
                if self._percentage == 0:
                    self._percentage = ordered_list_item_to_percentage(SPEED_LIST, "low")
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        is_success = await self.hass.async_add_executor_job(
            assistant.set_air_fresh_power,
            self._dev_no,
            self._dev_ch,
            False,
        )
        if is_success:
            self._is_on = False
            self.async_write_ha_state()

    async def async_set_percentage(self, percentage):
        if percentage == 0:
            await self.async_turn_off()
        else:
            speed = percentage_to_ordered_list_item(SPEED_LIST, percentage)
            wind_speed = SPEED_MAP[speed]
            is_success = await self.hass.async_add_executor_job(
                assistant.set_air_fresh_wind_speed,
                self._dev_no,
                self._dev_ch,
                wind_speed,
            )
            if is_success:
                self._percentage = percentage
                self._is_on = True
                self.async_write_ha_state()

    def update_state(self, state):
        reports = state.get("reports", {})
        power_on = reports.get("powerOn", 0)
        wind_speed = reports.get("windSpeed", 1)
        
        self._is_on = power_on == 1
        
        if self._is_on and wind_speed in [1, 2, 3]:
            speed_name = next((k for k, v in SPEED_MAP.items() if v == wind_speed), "low")
            self._percentage = ordered_list_item_to_percentage(SPEED_LIST, speed_name)
        else:
            self._percentage = 0
        
        self.async_write_ha_state()