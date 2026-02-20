"""Constants for TellStick Local integration."""
from __future__ import annotations

DOMAIN = "tellstick_local"

# Config keys (CONF_HOST from homeassistant.const is used for host)
CONF_COMMAND_PORT = "command_port"
CONF_EVENT_PORT = "event_port"
CONF_AUTOMATIC_ADD = "automatic_add"

# Defaults
DEFAULT_HOST = "localhost"
DEFAULT_COMMAND_PORT = 50800
DEFAULT_EVENT_PORT = 50801
DEFAULT_AUTOMATIC_ADD = False

# telldusd event types
TELLDUSD_DEVICE_EVENT = 1
TELLDUSD_DEVICE_CHANGE = 2
TELLDUSD_RAW_DEVICE_EVENT = 3
TELLDUSD_SENSOR_EVENT = 4

# TellStick device methods (from telldus-core constants)
TELLSTICK_TURNON = 1
TELLSTICK_TURNOFF = 2
TELLSTICK_BELL = 4
TELLSTICK_DIM = 16
TELLSTICK_UP = 128
TELLSTICK_DOWN = 256
TELLSTICK_STOP = 512

# Sensor data types
TELLSTICK_TEMPERATURE = 1
TELLSTICK_HUMIDITY = 2
TELLSTICK_RAINRATE = 4
TELLSTICK_RAINTOTAL = 8
TELLSTICK_WINDDIRECTION = 16
TELLSTICK_WINDAVERAGE = 32
TELLSTICK_WINDGUST = 64

# HA platforms
PLATFORMS = ["switch", "light", "sensor"]

# Entry data keys
ENTRY_TELLSTICK_CONTROLLER = "controller"

# Signal for new device discovery
SIGNAL_NEW_DEVICE = DOMAIN + "_new_device_{}"
SIGNAL_EVENT = DOMAIN + "_event_{}"
