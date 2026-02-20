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
# Device catalog — user-friendly brand/device picker → (protocol, model)
# Extracted from TelldusCenter 2.1.2 (TelldusGui/data/telldus/devices.xml).
# Each entry: (label, protocol, model).  The model includes the vendor suffix
# after ":" exactly as TelldusCenter sends it to telldusd.
# Popular Nordic brands (Nexa, Proove, KlikAanKlikUit) are listed first.
# ---------------------------------------------------------------------------
DEVICE_CATALOG: list[tuple[str, str, str]] = [
    # --- Nexa (most popular Nordic brand) ---
    ("Nexa — Self-learning on/off", "arctech", "selflearning-switch:nexa"),
    ("Nexa — Self-learning dimmer", "arctech", "selflearning-dimmer:nexa"),
    ("Nexa — Code switch", "arctech", "codeswitch:nexa"),
    ("Nexa — Bell", "arctech", "bell:nexa"),
    # --- Proove ---
    ("Proove — Self-learning on/off", "arctech", "selflearning-switch:proove"),
    ("Proove — Self-learning dimmer", "arctech", "selflearning-dimmer:proove"),
    ("Proove — Code switch", "arctech", "codeswitch:proove"),
    ("Proove — Bell", "arctech", "bell:proove"),
    # --- KlikAanKlikUit (KAKU) ---
    ("KlikAanKlikUit — Self-learning on/off", "arctech", "selflearning-switch:klikaanklikuit"),
    ("KlikAanKlikUit — Self-learning dimmer", "arctech", "selflearning-dimmer:klikaanklikuit"),
    ("KlikAanKlikUit — Code switch", "arctech", "codeswitch:klikaanklikuit"),
    ("KlikAanKlikUit — Bell", "arctech", "bell:klikaanklikuit"),
    # --- Intertechno ---
    ("Intertechno — Self-learning on/off", "arctech", "selflearning-switch:intertechno"),
    ("Intertechno — Self-learning dimmer", "arctech", "selflearning-dimmer:intertechno"),
    ("Intertechno — Code switch", "arctech", "codeswitch:intertechno"),
    ("Intertechno — Bell", "arctech", "bell:intertechno"),
    # --- HomeEasy ---
    ("HomeEasy — Self-learning on/off", "arctech", "selflearning-switch:homeeasy"),
    ("HomeEasy — Self-learning dimmer", "arctech", "selflearning-dimmer:homeeasy"),
    ("HomeEasy — Code switch", "arctech", "codeswitch:homeeasy"),
    # --- Chacon ---
    ("Chacon — Self-learning on/off", "arctech", "selflearning-switch:chacon"),
    ("Chacon — Self-learning dimmer", "arctech", "selflearning-dimmer:chacon"),
    ("Chacon — Code switch", "arctech", "codeswitch:chacon"),
    ("Chacon — Bell", "arctech", "bell:chacon"),
    # --- CoCo Technologies ---
    ("CoCo Technologies — Self-learning on/off", "arctech", "selflearning-switch:coco"),
    ("CoCo Technologies — Self-learning dimmer", "arctech", "selflearning-dimmer:coco"),
    ("CoCo Technologies — Code switch", "arctech", "codeswitch:coco"),
    ("CoCo Technologies — Bell", "arctech", "bell:coco"),
    # --- Kappa ---
    ("Kappa — Self-learning on/off", "arctech", "selflearning-switch:kappa"),
    ("Kappa — Self-learning dimmer", "arctech", "selflearning-dimmer:kappa"),
    ("Kappa — Code switch", "arctech", "codeswitch:kappa"),
    ("Kappa — Bell", "arctech", "bell:kappa"),
    # --- Bye Bye Standby ---
    ("Bye Bye Standby — Code switch", "arctech", "codeswitch:byebyestandby"),
    # --- Anslut / Jula ---
    ("Anslut — Self-learning on/off", "comen", "selflearning-switch:jula"),
    # --- Brennenstuhl ---
    ("Brennenstuhl — Code switch", "sartano", "codeswitch:brennenstuhl"),
    # --- Conrad ---
    ("Conrad — Self-learning", "risingsun", "selflearning:conrad"),
    # --- Ecosavers ---
    ("Ecosavers — Self-learning", "silvanchip", "ecosavers:ecosavers"),
    # --- Elro ---
    ("Elro — Code switch", "sartano", "codeswitch:elro"),
    ("Elro — Code switch (AB600)", "arctech", "codeswitch:elro-ab600"),
    # --- GAO / Everflourish ---
    ("GAO — Self-learning on/off", "everflourish", "selflearning-switch:gao"),
    ("GAO — Code switch", "risingsun", "codeswitch:gao"),
    # --- Goobay ---
    ("Goobay — Code switch", "yidong", "goobay:goobay"),
    # --- HQ ---
    ("HQ — Code switch", "fuhaote", "codeswitch:fuhaote"),
    # --- IKEA ---
    ("IKEA — Koppla on/off", "ikea", "selflearning-switch:ikea"),
    ("IKEA — Koppla dimmer", "ikea", "selflearning:ikea"),
    # --- Kjell & Company ---
    ("Kjell & Company — Code switch", "risingsun", "codeswitch:kjelloco"),
    # --- Otio ---
    ("Otio — Self-learning", "risingsun", "selflearning:otio"),
    # --- Rusta ---
    ("Rusta — Code switch", "sartano", "codeswitch:rusta"),
    ("Rusta — Self-learning dimmer", "arctech", "selflearning-dimmer:rusta"),
    # --- Sartano ---
    ("Sartano — Code switch", "sartano", "codeswitch:sartano"),
    # --- UPM ---
    ("UPM — Self-learning", "upm", "selflearning:upm"),
    # --- Waveman ---
    ("Waveman — Code switch", "waveman", "codeswitch:waveman"),
    # --- X10 ---
    ("X10 — Code switch", "x10", "codeswitch:x10"),
    # --- Blinds / projector screens ---
    ("Hasta — Blinds", "hasta", "selflearning:hasta"),
    ("Hasta — Blinds (v2)", "hasta", "selflearningv2:hasta"),
    ("Rollertrol — Blinds", "hasta", "selflearningv2:rollertrol"),
    ("Roxcore — Projector screen", "brateck", "codeswitch:roxcore"),
    ("KingPin — KP100", "silvanchip", "kp100:kingpin"),
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
    """Build a stable device UID normalized to match raw RF event model strings.

    The model field from the device catalog may include a vendor suffix after ":"
    (e.g. "selflearning-switch:nexa").  Raw RF events only report the base model
    (e.g. "selflearning"), so we strip the suffix and then normalize.
    """
    # Strip vendor suffix (e.g. "selflearning-switch:nexa" → "selflearning-switch")
    base_model = model.split(":")[0] if ":" in model else model
    uid_model = _UID_MODEL_NORMALIZE.get(base_model, base_model)
    return "_".join(filter(None, [protocol, uid_model, house, unit]))
