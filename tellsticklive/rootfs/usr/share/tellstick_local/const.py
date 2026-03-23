"""Constants for TellStick Local integration."""
from __future__ import annotations

DOMAIN = "tellstick_local"

# Must match manifest.json "version".  Frozen at import time so the
# integration can detect when on-disk files were updated behind a
# running HA instance (i.e. the app copied a newer version but HA
# hasn't restarted yet).
#
# VERSION BUMP RULES — ALWAYS run `git branch --show-current` first:
#   X.Y.Z.W
#   W → bump for each prompt on the SAME branch (same feature branch)
#   Z → bump ONLY when working on a NEW branch (different branch name)
#   Y → minor feature release
#   X → major release
#
#   Trigger for Z: the git branch name changes.  That's it.
#   A new agent context window on the SAME branch is still a W bump.
#   Run `git branch --show-current` — if the branch matches the memory,
#   bump W.  If it's a different branch, bump Z.
#
#   BUMP ALL FOUR FILES — they must always be identical:
#     1. custom_components/tellstick_local/manifest.json          ("version")
#     2. custom_components/tellstick_local/const.py               (INTEGRATION_VERSION)
#     3. tellsticklive/rootfs/usr/share/tellstick_local/manifest.json  ("version")
#     4. tellsticklive/rootfs/usr/share/tellstick_local/const.py  (INTEGRATION_VERSION)
INTEGRATION_VERSION = "2.4.13.3"

# Backend type stored in config entry data
CONF_BACKEND = "backend"
BACKEND_DUO = "duo"   # TellStick Duo — TCP via socat bridges to telldusd
BACKEND_NET = "net"   # TellStick Net / ZNet — UDP protocol direct to device

# Net/ZNet UDP ports
NET_DISCOVERY_PORT = 30303    # broadcast "D" → device replies with IP/MAC/firmware
NET_COMMAND_PORT = 42314      # "reglistener" + "send" commands; ZNet pushes events here
NET_REGISTRATION_INTERVAL_MINUTES = 10  # re-send "reglistener" every 10 minutes

# Config keys (CONF_HOST from homeassistant.const is used for host)
CONF_COMMAND_PORT = "command_port"
CONF_EVENT_PORT = "event_port"
CONF_AUTOMATIC_ADD = "automatic_add"
CONF_DETECT_SARTANO = "detect_sartano"
# Device storage keys (in entry.options["devices"])
CONF_DEVICES = "devices"
CONF_DEVICE_PROTOCOL = "protocol"
CONF_DEVICE_MODEL = "model"
CONF_DEVICE_HOUSE = "house"
CONF_DEVICE_UNIT = "unit"
CONF_DEVICE_NAME = "name"
CONF_IGNORED_UIDS = "ignored_uids"

# Defaults
DEFAULT_HOST = ""  # empty by design — actual hostname is shown in the app log ("use host: …")
DEFAULT_COMMAND_PORT = 50800
DEFAULT_EVENT_PORT = 50801
DEFAULT_AUTOMATIC_ADD = True
DEFAULT_DETECT_SARTANO = False

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

# Human-readable names for the sensor data types above
SENSOR_TYPE_NAMES: dict[int, str] = {
    TELLSTICK_TEMPERATURE: "temperature",
    TELLSTICK_HUMIDITY: "humidity",
    TELLSTICK_RAINRATE: "rain_rate",
    TELLSTICK_RAINTOTAL: "rain_total",
    TELLSTICK_WINDDIRECTION: "wind_direction",
    TELLSTICK_WINDAVERAGE: "wind_speed",
    TELLSTICK_WINDGUST: "wind_gust",
}

# HA platforms
PLATFORMS = ["button", "cover", "switch", "light", "sensor"]

# Entry data keys
ENTRY_TELLSTICK_CONTROLLER = "controller"
ENTRY_DEVICE_ID_MAP = "device_id_map"

# Signal for new device discovery
SIGNAL_NEW_DEVICE = DOMAIN + "_new_device_{}"
SIGNAL_EVENT = DOMAIN + "_event_{}"

# TX-capable protocols (can send commands and teach self-learning devices)
# Source: telldus-core Protocol.cpp::getProtocolInstance() — only protocols
# listed there can be instantiated to send RF commands.
# NOTE: "mandolyn" is intentionally absent — it is RX-only (temperature/
# humidity sensors).  ProtocolMandolyn has no methods() or getStringForMethod()
# and is not registered in getProtocolInstance().
# NOTE: "fineoffset" and "oregon" are also RX-only sensor protocols.
TX_PROTOCOLS = [
    "arctech",
    "brateck",
    "comen",
    "everflourish",
    "fuhaote",
    "hasta",
    "ikea",
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
    "risingsun": "",
    "sartano": "",
    "silvanchip": "",
    "upm": "",
    "waveman": "",
    "x10": "",
    "yidong": "",
}

# ---------------------------------------------------------------------------
# Widget parameter definitions — from TelldusCenter 2.1.2
# (telldus-gui-2.1.2/TelldusGui/editdevicedialog.cpp)
#
# Each widget ID maps to a list of field specs.  A field spec is a dict:
#   name     – telldusd parameter name (e.g. "house", "unit", "code")
#   type     – "int", "letter", "str", or "bool"
#   default  – default value
#   min/max  – for "int": numeric bounds; for "letter": start/end character
#   random   – True if the field should get a random default
# ---------------------------------------------------------------------------
WIDGET_PARAMS: dict[int, list[dict]] = {
    # 1: DeviceSettingNexa – arctech codeswitch, waveman, x10, byebye, elro-ab600
    1: [
        {"name": "house", "type": "letter", "default": "A", "min": "A", "max": "P"},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 16},
    ],
    # 2: DeviceSettingSartano – sartano, fuhaote
    2: [
        {"name": "code", "type": "str", "default": "0000000000"},
    ],
    # 3: DeviceSettingIkea
    3: [
        {"name": "system", "type": "int", "default": 1, "min": 1, "max": 16},
        {"name": "units", "type": "str", "default": "1"},
        {"name": "fade", "type": "bool", "default": False},
    ],
    # 4: DeviceSettingNexaBell – arctech bell (house only, no unit)
    4: [
        {"name": "house", "type": "letter", "default": "A", "min": "A", "max": "P"},
    ],
    # 5: DeviceSettingRisingSun – risingsun codeswitch (Kjell & Company)
    5: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 4},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 4},
    ],
    # 6: DeviceSettingBrateck – brateck (8-char string of 0/-/1)
    6: [
        {"name": "house", "type": "str", "default": "00000000"},
    ],
    # 8: DeviceSettingArctechSelflearning – default (26-bit house)
    8: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 67108863, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 16},
    ],
    # 9: ArctechSelflearning – UPM (house 0-4095, unit 1-4)
    9: [
        {"name": "house", "type": "int", "default": 0, "min": 0, "max": 4095},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 4},
    ],
    # 10: DeviceSettingGAO – risingsun codeswitch:gao (4 houses × 3 units)
    10: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 4},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 3},
    ],
    # 11: ArctechSelflearning – everflourish (house 0-16383, unit 1-4)
    11: [
        {"name": "house", "type": "int", "default": 0, "min": 0, "max": 16383, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 4},
    ],
    # 12: ArctechSelflearning – risingsun selflearning (Conrad, Otio)
    12: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 33554432, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 16},
    ],
    # 13: DeviceSettingUnitcode – yidong (Goobay) – unit only
    13: [
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 4},
    ],
    # 14: ArctechSelflearning – silvanchip ecosavers
    14: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 1048575, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 4},
    ],
    # 15: DeviceSettingSelflearning – silvanchip KP100 (house only)
    15: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 1048575, "random": True},
    ],
    # 16: ArctechSelflearning – hasta blinds
    16: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 65536, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 15},
    ],
    # 17: ArctechSelflearning – comen (Anslut/Jula)
    17: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 16777215, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 16},
    ],
}

# ---------------------------------------------------------------------------
# Device catalog — user-friendly brand/device picker → (protocol, model, widget)
# Extracted from TelldusCenter 2.1.2 (TelldusGui/data/telldus/devices.xml).
# Each entry: (label, protocol, model, widget).  The model includes the vendor
# suffix after ":" exactly as TelldusCenter sends it to telldusd.
# The widget number selects the parameter form (ranges/defaults) from
# WIDGET_PARAMS above.
# Popular Nordic brands (Nexa, Proove, KlikAanKlikUit) are listed first.
# ---------------------------------------------------------------------------
DEVICE_CATALOG: list[tuple[str, str, str, int]] = [
    ("Anslut — Self-learning on/off", "comen", "selflearning-switch:jula", 17),
    ("Brennenstuhl — Code switch", "sartano", "codeswitch:brennenstuhl", 2),
    ("Bye Bye Standby — Code switch", "arctech", "codeswitch:byebyestandby", 1),
    ("Chacon — Bell", "arctech", "bell:chacon", 4),
    ("Chacon — Code switch", "arctech", "codeswitch:chacon", 1),
    ("Chacon — Self-learning dimmer", "arctech", "selflearning-dimmer:chacon", 8),
    ("Chacon — Self-learning on/off", "arctech", "selflearning-switch:chacon", 8),
    ("CoCo Technologies — Bell", "arctech", "bell:coco", 4),
    ("CoCo Technologies — Code switch", "arctech", "codeswitch:coco", 1),
    ("CoCo Technologies — Self-learning dimmer", "arctech", "selflearning-dimmer:coco", 8),
    ("CoCo Technologies — Self-learning on/off", "arctech", "selflearning-switch:coco", 8),
    ("Conrad — Self-learning", "risingsun", "selflearning:conrad", 12),
    ("Ecosavers — Self-learning", "silvanchip", "ecosavers:ecosavers", 14),
    ("Elro — Code switch", "sartano", "codeswitch:elro", 2),
    ("Elro — Code switch (AB600)", "arctech", "codeswitch:elro-ab600", 1),
    ("GAO — Code switch", "risingsun", "codeswitch:gao", 10),
    ("GAO — Self-learning on/off", "everflourish", "selflearning-switch:gao", 11),
    ("Goobay — Code switch", "yidong", "goobay:goobay", 13),
    ("Hasta — Blinds", "hasta", "selflearning:hasta", 16),
    ("Hasta — Blinds (v2)", "hasta", "selflearningv2:hasta", 16),
    ("HomeEasy — Code switch", "arctech", "codeswitch:homeeasy", 1),
    ("HomeEasy — Self-learning dimmer", "arctech", "selflearning-dimmer:homeeasy", 8),
    ("HomeEasy — Self-learning on/off", "arctech", "selflearning-switch:homeeasy", 8),
    ("HQ — Code switch", "fuhaote", "codeswitch:fuhaote", 2),
    ("IKEA — Koppla dimmer", "ikea", "selflearning:ikea", 3),
    ("IKEA — Koppla on/off", "ikea", "selflearning-switch:ikea", 3),
    ("Intertechno — Bell", "arctech", "bell:intertechno", 4),
    ("Intertechno — Code switch", "arctech", "codeswitch:intertechno", 1),
    ("Intertechno — Self-learning dimmer", "arctech", "selflearning-dimmer:intertechno", 8),
    ("Intertechno — Self-learning on/off", "arctech", "selflearning-switch:intertechno", 8),
    ("Kappa — Bell", "arctech", "bell:kappa", 4),
    ("Kappa — Code switch", "arctech", "codeswitch:kappa", 1),
    ("Kappa — Self-learning dimmer", "arctech", "selflearning-dimmer:kappa", 8),
    ("Kappa — Self-learning on/off", "arctech", "selflearning-switch:kappa", 8),
    ("KingPin — KP100", "silvanchip", "kp100:kingpin", 15),
    ("Kjell & Company — Code switch", "risingsun", "codeswitch:kjelloco", 5),
    ("KlikAanKlikUit — Bell", "arctech", "bell:klikaanklikuit", 4),
    ("KlikAanKlikUit — Code switch", "arctech", "codeswitch:klikaanklikuit", 1),
    ("KlikAanKlikUit — Self-learning dimmer", "arctech", "selflearning-dimmer:klikaanklikuit", 8),
    ("KlikAanKlikUit — Self-learning on/off", "arctech", "selflearning-switch:klikaanklikuit", 8),
    # Lidl/Silvercrest 433 MHz sockets use arctech selflearning protocol
    ("Lidl (Silvercrest) — Self-learning on/off", "arctech", "selflearning-switch:silvercrest", 8),
    # NOTE: Luxorparts/Cleverio 50969, 50970, 50972 removed — NOT WORKING (see README Known limitations)
    ("Nexa — Bell", "arctech", "bell:nexa", 4),
    ("Nexa — Code switch", "arctech", "codeswitch:nexa", 1),
    ("Nexa — Self-learning dimmer", "arctech", "selflearning-dimmer:nexa", 8),
    ("Nexa — Self-learning on/off", "arctech", "selflearning-switch:nexa", 8),
    ("Otio — Self-learning", "risingsun", "selflearning:otio", 12),
    # Profile is a Nordic/Norwegian brand using arctech selflearning
    ("Profile — Self-learning on/off", "arctech", "selflearning-switch:profile", 8),
    ("Proove — Bell", "arctech", "bell:proove", 4),
    ("Proove — Code switch", "arctech", "codeswitch:proove", 1),
    ("Proove — Self-learning dimmer", "arctech", "selflearning-dimmer:proove", 8),
    ("Proove — Self-learning on/off", "arctech", "selflearning-switch:proove", 8),
    ("Rollertrol — Blinds", "hasta", "selflearningv2:rollertrol", 16),
    ("Roxcore — Projector screen", "brateck", "codeswitch:roxcore", 6),
    ("Rusta — Code switch", "sartano", "codeswitch:rusta", 2),
    ("Rusta — Self-learning dimmer", "arctech", "selflearning-dimmer:rusta", 8),
    ("Rusta — Self-learning on/off", "arctech", "selflearning-switch:rusta", 8),
    ("Sartano — Code switch", "sartano", "codeswitch:sartano", 2),
    # Telldus own-branded devices use arctech selflearning protocol
    ("Telldus — Self-learning dimmer", "arctech", "selflearning-dimmer:telldus", 8),
    ("Telldus — Self-learning on/off", "arctech", "selflearning-switch:telldus", 8),
    # Trust Smart Home (Netherlands) uses arctech selflearning
    ("Trust Smart Home — Self-learning dimmer", "arctech", "selflearning-dimmer:trust", 8),
    ("Trust Smart Home — Self-learning on/off", "arctech", "selflearning-switch:trust", 8),
    ("UPM — Self-learning", "upm", "selflearning:upm", 9),
    ("Waveman — Code switch", "waveman", "codeswitch:waveman", 1),
    ("X10 — Code switch", "x10", "codeswitch:x10", 1),
]

# Build a lookup dict: label → (protocol, model, widget)
DEVICE_CATALOG_MAP: dict[str, tuple[str, str, int]] = {
    label: (proto, model, widget)
    for label, proto, model, widget in DEVICE_CATALOG
}

# Ordered list of labels for the dropdown
DEVICE_CATALOG_LABELS: list[str] = [label for label, _, _, _ in DEVICE_CATALOG]

# ---------------------------------------------------------------------------
# Protocol catalog — same structure as DEVICE_CATALOG but organised by
# protocol name rather than brand name.  One entry per distinct
# (protocol, model) combination; the vendor suffix is omitted so the model
# field matches what telldusd receives after stripping.
# Users who know their RF protocol can use this list instead of searching
# through dozens of brand names.
# ---------------------------------------------------------------------------
PROTOCOL_MODEL_CATALOG: list[tuple[str, str, str, int]] = [
    # arctech — most common EU/Nordic 433 MHz protocol (TX+RX)
    ("arctech — Bell", "arctech", "bell", 4),
    ("arctech — Code switch", "arctech", "codeswitch", 1),
    ("arctech — Self-learning dimmer", "arctech", "selflearning-dimmer", 8),
    ("arctech — Self-learning on/off", "arctech", "selflearning-switch", 8),
    # brateck — projector screens / blinds (TX only)
    ("brateck — Blinds / projector screen", "brateck", "codeswitch", 6),
    # comen — Anslut / Jula brand (TX only)
    ("comen — Self-learning on/off", "comen", "selflearning-switch", 17),
    # everflourish — GAO selflearning (TX+RX)
    ("everflourish — Self-learning on/off", "everflourish", "selflearning-switch", 11),
    # fuhaote — HQ brand code switch (TX only)
    ("fuhaote — Code switch", "fuhaote", "codeswitch", 2),
    # hasta — motorised blinds / Rollertrol (TX+RX)
    ("hasta — Blinds (v1 / older motors)", "hasta", "selflearning", 16),
    ("hasta — Blinds (v2 / newer motors, Rollertrol)", "hasta", "selflearningv2", 16),
    # ikea — Koppla 433 MHz (TX only)
    ("ikea — Koppla dimmer", "ikea", "selflearning", 3),
    ("ikea — Koppla on/off", "ikea", "selflearning-switch", 3),
    # risingsun — Kjell & Company, Conrad, Otio (TX+RX)
    ("risingsun — Code switch", "risingsun", "codeswitch", 5),
    ("risingsun — Self-learning on/off", "risingsun", "selflearning", 12),
    # sartano — Brennenstuhl, Elro, Rusta code switch (TX+RX)
    ("sartano — Code switch", "sartano", "codeswitch", 2),
    # silvanchip — Ecosavers, KingPin KP100 (TX only)
    ("silvanchip — Ecosavers", "silvanchip", "ecosavers", 14),
    ("silvanchip — KP100", "silvanchip", "kp100", 15),
    # upm — UPM selflearning (TX only)
    ("upm — Self-learning on/off", "upm", "selflearning", 9),
    # waveman — old arctech family (TX+RX)
    ("waveman — Code switch", "waveman", "codeswitch", 1),
    # x10 — X10 protocol (TX+RX)
    ("x10 — Code switch", "x10", "codeswitch", 1),
    # yidong — Goobay remotes (TX only)
    ("yidong — Code switch", "yidong", "goobay", 13),
]

# Build a lookup dict: label → (protocol, model, widget)
PROTOCOL_MODEL_MAP: dict[str, tuple[str, str, int]] = {
    label: (proto, model, widget)
    for label, proto, model, widget in PROTOCOL_MODEL_CATALOG
}

# Ordered list of labels for the protocol dropdown
PROTOCOL_MODEL_LABELS: list[str] = [label for label, _, _, _ in PROTOCOL_MODEL_CATALOG]

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
    (e.g. ``selflearning-switch:nexa``).  Raw RF events report only the base model
    (e.g. ``selflearning``), so we:
    1. Strip the vendor suffix: ``selflearning-switch:nexa`` → ``selflearning-switch``
    2. Normalize: ``selflearning-switch`` → ``selflearning`` (to match RF events)
    """
    # Strip vendor suffix (e.g. "selflearning-switch:nexa" → "selflearning-switch")
    base_model = normalize_rf_model(model)
    return "_".join(filter(None, [protocol, base_model, house, unit]))


def normalize_rf_model(model: str) -> str:
    """Normalize a catalog model name to match what telldusd RF events report.

    Strips vendor suffix (``selflearning-switch:luxorparts`` →
    ``selflearning-switch``) then normalizes (``selflearning-switch`` →
    ``selflearning``) so UIDs match raw RF events.
    """
    base = model.split(":")[0] if ":" in model else model
    return _UID_MODEL_NORMALIZE.get(base, base)

