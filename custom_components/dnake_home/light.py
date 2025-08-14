import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.light import (
    LightEntity,
    ColorMode,
)
from homeassistant.helpers.entity import DeviceInfo
from .core.assistant import assistant
from .core.constant import DOMAIN, MANUFACTURER


_LOGGER = logging.getLogger(__name__)


def load_lights(device_list):
    lights = [DnakeLight(device) for device in device_list if device.get("devType") == 256]
    _LOGGER.error(f"find light num: {len(lights)}")
    assistant.entries["light"] = lights


def update_lights_state(states):
    lights = assistant.entries["light"]
    if not states:
        _LOGGER.warning("No states received for light update")
        return
        
    _LOGGER.debug(f"Updating {len(lights)} lights with {len(states)} states")
    
    for light in lights:
        try:
            state = next((state for state in states if light.is_hint_state(state)), None)
            if state:
                _LOGGER.debug(f"Updating light {light.name} with state: {state}")
                light.update_state(state)
            else:
                _LOGGER.debug(f"No matching state found for light {light.name}")
        except Exception as e:
            _LOGGER.error(f"Error updating light {light.name}: {e}")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    light_list = assistant.entries["light"]
    if light_list:
        # 为每个灯光实体设置hass引用
        for light in light_list:
            light.hass = hass
        async_add_entities(light_list)


class DnakeLight(LightEntity):

    def __init__(self, device):
        self._name = device.get("devName")
        gateway_info = device.get("gatewayDeviceInfo", {})
        self._dev_no = gateway_info.get("devNo")
        self._dev_ch = gateway_info.get("devCh")
        self._is_on = False
        self._available = True  # 添加可用性状态

    def is_hint_state(self, state):
        return state.get("devNo") == self._dev_no and state.get("devCh") == self._dev_ch

    @property
    def unique_id(self):
        return f"dnake_{self._dev_ch}_{self._dev_no}"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"light_{self._dev_ch}_{self._dev_no}")},
            name=self._name,
            manufacturer=MANUFACTURER,
            model="灯光控制",
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
    def available(self):
        return self._available

    @property
    def color_mode(self):
        return ColorMode.ONOFF

    @property
    def supported_color_modes(self):
        return {ColorMode.ONOFF}

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"Turning on light: {self._name}")
        await self._turn_to(True)

    async def async_turn_off(self, **kwargs):
        _LOGGER.info(f"Turning off light: {self._name}")
        await self._turn_to(False)

    async def _turn_to(self, is_on):
        _LOGGER.info(f"Setting light {self._name} to: {is_on}")
        is_success = await self.hass.async_add_executor_job(
            assistant.turn_to,
            self._dev_no,
            self._dev_ch,
            is_on,
        )
        if is_success:
            old_state = self._is_on
            self._is_on = is_on
            _LOGGER.info(f"Light {self._name} state changed from {old_state} to {self._is_on}")
            # 强制更新状态
            self.async_write_ha_state()
            # 确保状态更新被处理
            if hasattr(self, 'hass') and self.hass:
                self.hass.async_create_task(self._ensure_state_update())
        else:
            _LOGGER.error(f"Failed to set light {self._name} to {is_on}")

    async def _ensure_state_update(self):
        """确保状态更新被正确处理"""
        await self.hass.async_add_executor_job(lambda: None)
        self.async_write_ha_state()

    def update_state(self, state):
        if not state:
            return
            
        old_state = self._is_on
        new_state = state.get("state", 0) == 1
        
        if old_state != new_state:
            self._is_on = new_state
            _LOGGER.info(f"Light {self._name} state updated from gateway: {old_state} -> {self._is_on}")
            # 强制更新状态
            self.async_write_ha_state()
            # 添加额外的状态更新确认
            self._schedule_extra_update()
        else:
            _LOGGER.debug(f"Light {self._name} state unchanged: {self._is_on}")

    def _schedule_extra_update(self):
        """安排额外的状态更新以确保UI刷新"""
        if hasattr(self, 'hass') and self.hass:
            try:
                # 延迟100ms后再次更新状态
                self.hass.async_create_task(self._delayed_state_update())
            except Exception as e:
                _LOGGER.error(f"Failed to schedule extra update for {self._name}: {e}")

    async def _delayed_state_update(self):
        """延迟状态更新"""
        import asyncio
        await asyncio.sleep(0.1)  # 100ms延迟
        try:
            self.async_write_ha_state()
            _LOGGER.debug(f"Extra state update completed for {self._name}")
        except Exception as e:
            _LOGGER.error(f"Extra state update failed for {self._name}: {e}")
