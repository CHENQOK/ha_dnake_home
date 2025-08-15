import logging
import requests

from .constant import Action, Cmd, Power
from .utils import encode_auth, get_uuid

_LOGGER = logging.getLogger(__name__)


class __AssistantCore:
    def __init__(self):
        self.gw_ip = None
        self.auth = None
        self.from_device = None
        self.to_device = None
        self.entries = {}

    def bind_auth_info(self, gw_ip, auth_name, auth_psw):
        self.gw_ip = gw_ip
        self.auth = encode_auth(auth_name, auth_psw)
        _LOGGER.info(f"bind auth info: ip={self.gw_ip},auth={self.auth}")

    def bind_iot_info(self, iot_device_name, gw_iot_name):
        self.from_device = iot_device_name
        self.to_device = gw_iot_name
        _LOGGER.info(f"bind iot info: from={self.from_device},to={self.to_device}")

    def _get_url(self, path):
        return f"http://{self.gw_ip}{path}"

    def _get_header(self):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.auth}",
        }

    def get(self, path):
        try:
            url = self._get_url(path)
            resp = requests.get(url, headers=self._get_header())
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            _LOGGER.error("get error: path=%s,err=%s", path, e)
            return None

    def post(self, data: dict):
        try:
            url = self._get_url("/route.cgi?api=request")
            data["uuid"] = get_uuid()
            resp = requests.post(
                url,
                headers=self._get_header(),
                json={
                    "fromDev": self.from_device,
                    "toDev": self.to_device,
                    "data": data,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            _LOGGER.error("post error: data=%s,err=%s", data, e)
            return None

    def do_action(self, data: dict):
        _LOGGER.error(f"post data: {data}")
        resp = self.post(data)
        _LOGGER.error(f"post resp: {resp}")
        return resp and resp.get("result") == "ok"


class Assistant(__AssistantCore):

    def query_iot_info(self):
        iot_info = self.get("/smart/iot.info")
        if iot_info:
            return {
                "iot_device_name": iot_info.get("devIotName"),
                "gw_iot_name": iot_info.get("gwIotName"),
            }
        else:
            _LOGGER.error("query iot info fail")
            return None

    def query_device_list(self):
        device_info = self.get("/smart/extra/device.info")
        if device_info:
            return device_info
        else:
            _LOGGER.error("query device info fail")
            return None

    def read_dev_state(self, dev_no, dev_ch, dev_type=None, code=None):
        data = {
            "action": Action.ReadDev.value,
            "devNo": dev_no,
            "devCh": dev_ch,
        }
        if dev_type is not None:
            data["devType"] = dev_type
        if code is not None and code != -1:
            data["code"] = code
            
        state_info = self.post(data)
        if state_info:
            return state_info
        else:
            _LOGGER.error(f"query device status fail: devNo={dev_no},devCh={dev_ch}")
            return None

    def read_all_dev_state(self, udid=0):
        """
        Read all device states - matches web interface API
        
        Args:
            udid: Device ID filter (default: 0 for all devices)
            
        Returns:
            list: Device list with state information, or None if failed
        """
        data = {
            "action": "readDev",
            "fields": "state", 
            "scope": "all",
            "index": 0,
            "udid": udid
        }
        
        state_info = self.post(data)
        if state_info and state_info.get("result") == "ok":
            dev_list = state_info.get("devList", [])
            page_no = state_info.get("pageNo", 1)
            total_page = state_info.get("totalPage", 1)
            
            _LOGGER.debug(f"read_all_dev_state response: {len(dev_list)} devices (page {page_no}/{total_page})")
            
            # Process device states from reports field
            processed_devices = []
            for device in dev_list:
                dev_no = device.get("devNo")
                dev_ch = device.get("devCh") 
                dev_type = device.get("devType")
                reports = device.get("reports", {})
                
                # Create processed device entry
                processed_device = {
                    "devNo": dev_no,
                    "devCh": dev_ch,
                    "devType": dev_type,
                    "reports": reports
                }
                
                # Add configs if present
                if "configs" in device:
                    processed_device["configs"] = device["configs"]
                    
                processed_devices.append(processed_device)
            _LOGGER.error(f"read_all_dev_state response: {processed_devices} devices")
            return processed_devices
        else:
            _LOGGER.error("query all device status fail")
            return None

    def read_all_dbus_devices(self):
        """Read all device profiles from dbus - matches JavaScript readAllDbusDevices"""
        data = {
            "action": Action.ReadDev.value,
            "fields": "profile",
            "scope": "all", 
            "index": 0
        }
        
        profile_info = self.post(data)
        if profile_info:
            return profile_info.get("devList")
        else:
            _LOGGER.error("query all device profiles fail")
            return None

    def update_device_list(self, exclude_dev_types=None, max_retries=3):
        """
        Complete device list update matching JavaScript Updatedevicelist function
        
        Args:
            exclude_dev_types: List of device types to exclude
            max_retries: Maximum retry attempts
            
        Returns:
            dict: Combined device information or None if failed
        """
        if exclude_dev_types is None:
            exclude_dev_types = []
            
        retry_count = 0
        
        while retry_count < max_retries:
            # Step 1: Get device states
            state_response = self.read_all_dev_state()
            
            if state_response:
                _LOGGER.debug(f"Device states retrieved: {len(state_response) if state_response else 0} devices")
                
                # Filter devices by type
                filtered_devices = []
                device_map = {}  # For quick lookup by devNo.devCh
                
                for device in state_response:
                    dev_type = device.get("devType")
                    if dev_type and dev_type not in exclude_dev_types:
                        filtered_devices.append(device)
                        key = f"{device.get('devNo')}.{device.get('devCh')}"
                        device_map[key] = device
                
                # Step 2: Get device profiles
                profile_response = self.read_all_dbus_devices()
                
                if profile_response:
                    _LOGGER.debug(f"Device profiles retrieved: {len(profile_response) if profile_response else 0} devices")
                    
                    # Step 3: Merge state and profile information
                    merged_devices = {}
                    
                    for profile_device in profile_response:
                        dev_no = profile_device.get("devNo")
                        if dev_no in [d.get("devNo") for d in filtered_devices]:
                            # Base device info from profile
                            merged_device = {
                                "devNo": dev_no,
                                "uid": profile_device.get("ieeeAddr"),
                                "modelId": profile_device.get("modleId"),  # Note: typo in original
                                "hwVer": profile_device.get("hwVer"),
                                "swVer": profile_device.get("swVer"),
                                "addr": profile_device.get("addr"),
                                "chList": {}
                            }
                            
                            # Add bus info if available
                            if profile_device.get("busNo"):
                                merged_device["busNo"] = profile_device.get("busNo")
                            if profile_device.get("busCh"):
                                merged_device["busCh"] = profile_device.get("busCh")
                            if profile_device.get("busType"):
                                merged_device["busType"] = profile_device.get("busType")
                            
                            # Merge channel information
                            profile_channels = profile_device.get("chList", [])
                            for channel in profile_channels:
                                dev_ch = channel.get("devCh")
                                key = f"{dev_no}.{dev_ch}"
                                
                                if key in device_map:
                                    # Merge state info with profile info
                                    merged_channel = device_map[key].copy()
                                    
                                    # Add profile-specific info
                                    if channel.get("productId"):
                                        merged_channel["productId"] = channel.get("productId")
                                    
                                    # Add binding information
                                    if channel.get("binds"):
                                        merged_channel["binds"] = []
                                        for bind in channel.get("binds", []):
                                            bind_info = {
                                                "devNo": bind.get("dstId"),
                                                "devCh": bind.get("dstEp")
                                            }
                                            merged_channel["binds"].append(bind_info)
                                    
                                    merged_device["chList"][dev_ch] = merged_channel
                            
                            # Set device count
                            merged_device["devCnt"] = len(merged_device["chList"])
                            merged_devices[dev_no] = merged_device
                    
                    _LOGGER.info(f"Successfully updated device list: {len(merged_devices)} devices")
                    return merged_devices
                
                else:
                    _LOGGER.warning("Failed to get device profiles, using state info only")
                    # Return state info only if profile fetch fails
                    devices_by_no = {}
                    for device in filtered_devices:
                        dev_no = device.get("devNo")
                        dev_ch = device.get("devCh")
                        
                        if dev_no not in devices_by_no:
                            devices_by_no[dev_no] = {
                                "devNo": dev_no,
                                "chList": {},
                                "devCnt": 0
                            }
                        
                        devices_by_no[dev_no]["chList"][dev_ch] = device
                        devices_by_no[dev_no]["devCnt"] = len(devices_by_no[dev_no]["chList"])
                    
                    return devices_by_no
            
            # Retry logic
            retry_count += 1
            if retry_count < max_retries:
                _LOGGER.warning(f"Device list update failed, retrying ({retry_count}/{max_retries})")
                import time
                time.sleep(0.4)  # Match JavaScript 400ms delay
        
        _LOGGER.error(f"Failed to update device list after {max_retries} attempts")
        return None

    def ctrl_dev(self, data: dict):
        """Generic device control method matching JavaScript ctrlDev"""
        data["action"] = Action.CtrlDev.value
        return self.do_action(data)

    def turn_to(self, dev_no, dev_ch, is_open: bool):
        cmd = Cmd.On if is_open else Cmd.Off
        return self.ctrl_dev(
            {
                "cmd": cmd.value,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def stop(self, dev_no, dev_ch):
        return self.ctrl_dev(
            {
                "cmd": Cmd.Stop.value,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def set_level(self, dev_no, dev_ch, level: int):
        return self.ctrl_dev(
            {
                "cmd": Cmd.Level.value,
                "level": level,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def set_air_condition_power(self, dev_no, dev_ch, is_open: bool):
        power = Power.On if is_open else Power.Off
        return self.ctrl_dev(
            {
                "cmd": Cmd.AirCondition.value,
                "powerOn": power.value,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def set_air_condition_temperature(self, dev_no, dev_ch, temp: int):
        _LOGGER.error(f"set_air_condition_temperature: {temp}")
        return self.ctrl_dev(
            {
                "cmd": Cmd.AirCondition.value,
                "temp": temp,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def set_air_condition_mode(self, dev_no, dev_ch, mode: int):
        return self.ctrl_dev(
            {
                "cmd": Cmd.AirCondition.value,
                "airMode": mode,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )

    def set_air_condition_fan(self, dev_no, dev_ch, mode: int):
        return self.ctrl_dev(
            {
                "cmd": Cmd.AirCondition.value,
                "windSpeed": mode,
                "devNo": dev_no,
                "devCh": dev_ch,
            }
        )


assistant = Assistant()
