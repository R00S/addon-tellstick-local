"""Constants for TellStick Local integration."""
from __future__ import annotations

DOMAIN = "tellstick_local"

# Config keys (CONF_HOST from homeassistant.const is used for host)
CONF_COMMAND_PORT = "command_port"
CONF_EVENT_PORT = "event_port"
CONF_AUTOMATIC_ADD = "automatic_add"

# Device storage keys (in entry.options["devices"])
CONF_DEVICES = "devices"
CONF_DEVICE_PROTOCOL = "protocol"
CONF_DEVICE_MODEL = "model"
CONF_DEVICE_HOUSE = "house"
CONF_DEVICE_UNIT = "unit"
CONF_DEVICE_NAME = "name"

# Defaults
DEFAULT_HOST = "tellsticklive"  # add-on slug = hostname on the Supervisor network
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
ENTRY_DEVICE_ID_MAP = "device_id_map"

# Signal for new device discovery
SIGNAL_NEW_DEVICE = DOMAIN + "_new_device_{}"
SIGNAL_EVENT = DOMAIN + "_event_{}"

# TX-capable protocols (can send commands and teach self-learning devices)
TX_PROTOCOLS = [
    "arctech",
    "brateck",
    "comen",
    "everflourish",
    "fuhaote",
    "hasta",
    "ikea",
    "mandolyn",
    "risingsun",
    "sartano",
    "silvanchip",
    "upm",
    "waveman",
    "x10",
    "yidong",
]

# Default model for each protocol when teaching a new device
PROTOCOL_DEFAULT_MODELS: dict[str, str] = {
    "arctech": "selflearning-switch",
    "brateck": "",
    "comen": "",
    "everflourish": "selflearning",
    "fuhaote": "",
    "hasta": "",
    "ikea": "",
    "mandolyn": "",
    "risingsun": "",
    "sartano": "",
    "silvanchip": "",
    "upm": "",
    "waveman": "",
    "x10": "",
    "yidong": "",
}

# ---------------------------------------------------------------------------
# Device catalog — user-friendly names → (protocol, model)
# Modelled after TelldusCenter / Telldus Live device picker.
# Each entry is a tuple (label, protocol, model).
# The label is what the user sees in the "Add device" dropdown.
# ---------------------------------------------------------------------------
DEVICE_CATALOG: list[tuple[str, str, str]] = [
    # --- Nexa / KAKU / Proove / HomeEasy / Intertechno (arctech) ---
    ("Nexa / Proove — Self-learning switch", "arctech", "selflearning-switch"),
    ("Nexa / Proove — Self-learning dimmer", "arctech", "selflearning-dimmer"),
    ("Nexa / KAKU — Code switch (old dial-based)", "arctech", "codeswitch"),
    ("Nexa — Doorbell", "arctech", "bell"),
    # --- Everflourish / Rusta ---
    ("Everflourish / Rusta — Self-learning switch", "everflourish", "selflearning"),
    # --- Hasta ---
    ("Hasta — Motorised blind", "hasta", ""),
    # --- Mandolyn / Summerbird ---
    ("Mandolyn / Summerbird — Switch", "mandolyn", ""),
    # --- Sartano / Kjell & Company ---
    ("Sartano / Kjell & Company — Switch", "sartano", ""),
    # --- Waveman ---
    ("Waveman — Switch", "waveman", ""),
    # --- X10 ---
    ("X10 — Switch", "x10", ""),
    # --- Brateck ---
    ("Brateck — Motorised blind", "brateck", ""),
    # --- IKEA ---
    ("IKEA Koppla — Switch", "ikea", ""),
    # --- Rising Sun ---
    ("Rising Sun — Switch", "risingsun", ""),
    # --- Other / less common ---
    ("Comen — Switch", "comen", ""),
    ("Fuhaote — Switch", "fuhaote", ""),
    ("Silvanchip — Switch", "silvanchip", ""),
    ("Yidong — Switch", "yidong", ""),
]

# Build a lookup dict: label → (protocol, model)
DEVICE_CATALOG_MAP: dict[str, tuple[str, str]] = {
    label: (proto, model) for label, proto, model in DEVICE_CATALOG
}

# Ordered list of labels for the dropdown
DEVICE_CATALOG_LABELS: list[str] = [label for label, _, _ in DEVICE_CATALOG]

# Model normalization: arctech selflearning devices always report "selflearning" in
# raw RF events regardless of whether they were configured as -switch or -dimmer.
# Stored UIDs must use this normalized form so they match auto-discovered event UIDs.
_UID_MODEL_NORMALIZE: dict[str, str] = {
    "selflearning-switch": "selflearning",
    "selflearning-dimmer": "selflearning",
}


def build_device_uid(protocol: str, model: str, house: str, unit: str) -> str:
    """Build a stable device UID normalized to match raw RF event model strings."""
    uid_model = _UID_MODEL_NORMALIZE.get(model, model)
    return "_".join(filter(None, [protocol, uid_model, house, unit]))
