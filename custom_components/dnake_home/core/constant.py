from enum import Enum

TITLE = "Dnake Home"
DOMAIN = "dnake_home"
MANUFACTURER = "Dnake"


class Action(Enum):
    # 获取单设备状态
    ReadDev = "readDev"
    # 获取所有设备状态
    ReadAllDevState = "readDev"
    # 控制设备
    CtrlDev = "ctrlDev"


class Cmd(Enum):
    # 灯.etc
    On = "On"
    # 灯.etc
    Off = "Off"
    # 窗帘.etc
    Stop = "stop"
    # 窗帘.etc
    Level = "level"
    # 空调
    AirCondition = "AirCondition"


class Power(Enum):
    On = 1
    Off = 0
