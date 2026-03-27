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



INTEGRATION_VERSION = "3.1.5.4"


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
# Mirror / range extender: stored in the mirror entry's data dict.
# Value is the entry_id of the primary TellStick that this entry mirrors.
CONF_MIRROR_OF = "mirror_of"
# Device storage keys (in entry.options["devices"])
CONF_DEVICES = "devices"
CONF_DEVICE_PROTOCOL = "protocol"
CONF_DEVICE_MODEL = "model"
CONF_DEVICE_HOUSE = "house"
CONF_DEVICE_UNIT = "unit"
CONF_DEVICE_NAME = "name"
CONF_DEVICE_ENCODING = "encoding"
ENCODING_RAW = "raw"
ENCODING_NATIVE = "native"
ENCODING_NATIVE_NOFIX = "native_nofix"
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
# Runtime list of mirror controllers (populated by mirror entries at setup)
ENTRY_MIRRORS = "_mirrors"

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
    "kangtai",
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
    "kangtai": "selflearning-switch",
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
    # 18: kangtai on/off (Clas Ohlson 36-8836) — Net/ZNet only
    18: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 65535, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 30},
    ],
    # 19: kangtai dimmer — Net/ZNet only
    19: [
        {"name": "house", "type": "int", "default": 1, "min": 1, "max": 65535, "random": True},
        {"name": "unit", "type": "int", "default": 1, "min": 1, "max": 126},
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
    # Clas Ohlson 36-8836 uses kangtai protocol (Net/ZNet only)
    ("Clas Ohlson — Self-learning on/off (36-8836)", "kangtai", "selflearning-switch:clasohlson", 18),
    ("Clas Ohlson — Self-learning dimmer (36-8836)", "kangtai", "selflearning-dimmer:clasohlson", 19),
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
    # kangtai — Clas Ohlson 36-8836 (Net/ZNet only, TX only)
    ("kangtai — Self-learning on/off", "kangtai", "selflearning-switch", 18),
    ("kangtai — Self-learning dimmer", "kangtai", "selflearning-dimmer", 19),
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

# ---------------------------------------------------------------------------
# Net/ZNet protocol split — native vs raw pulse
#
# The ZNet firmware's handleSend() routes UDP "send" commands through its
# built-in Python protocol stack.  This works for ALL protocols, but has
# bugs (unit+1 offset, missing parameters, no R/P prefixes).  We compensate
# for the unit+1 bug in _encode_generic_command(), but protocols that need
# extra parameters (code, system, fade) or custom R/P values will NOT work
# via the native path.
#
# Protocols with raw pulse-train encoders bypass all firmware bugs and work
# on every hardware version (v1, v2, ZNet).
#
# See docs/ZNET_PROTOCOL_PORTING_GUIDE.md for full details.
# ---------------------------------------------------------------------------

# Protocols with raw pulse-train encoders implemented in net_client.py.
# These bypass all ZNet firmware bugs and work on ALL hardware versions.
NET_RAW_PROTOCOLS: set[str] = {"arctech", "everflourish"}

# Split PROTOCOL_MODEL_CATALOG for Net/ZNet backends:
# - "raw" = our code encodes the pulse train (reliable on all hardware;
#   protocols with a dedicated encoder use it, others fall back to native)
# - "native" = firmware handles encoding (unit+1 bug compensated, but only
#   house/unit params passed — protocols needing code/system/fade may fail)
#
# BOTH catalogs contain ALL protocols so users can test either path for
# every device.  The encoding preference ("raw" or "native") is stored
# per device in CONF_DEVICE_ENCODING and checked at send time.

PROTOCOL_RAW_CATALOG: list[tuple[str, str, str, int]] = list(
    PROTOCOL_MODEL_CATALOG
)

# ---------------------------------------------------------------------------
# Everflourish encoding variants for ZNet/Net hardware testing.
#
# Split into TWO test devices:
#   1. RAW variants (ef_r01..ef_r52) — S-only pulse-train bytes that bypass
#      firmware protocol handling.  These make the ZNet LED blink.
#   2. NATIVE variants (ef_n01..ef_n53) — firmware protocol dicts that go
#      through the ZNet's handleSend() Python stack.  Currently do NOT make
#      the ZNet LED blink — exhaustive testing of the native path.
#
# The old ef_v1..ef_v20 are kept for backward compat (dispatched in
# _encode_everflourish_variant).
#
# See docs/EVERFLOURISH_RESEARCH.md for background.
# ---------------------------------------------------------------------------

# ---- RAW (S-only) test variants ------------------------------------------
# Group RS: Standard timing sweep with different R (repeat) values
# Group RT: Timing sweep — varying pulse widths
# Group RP: Preamble length sweep
# Group RD: Double/triple signal copies
# Group RF: Frame/terminator combinations
# Group RI: Inverted bit encoding
# Group RB: Bit order variations
# Group RX: Cross timing (short from one group, long from another)
_EF_TEST_RAW_VARIANTS: list[tuple[str, str, str, int]] = [
    # --- Group RS: Standard timing (60/114), varying repeat count ---
    ("EF raw r01 — S std R=1", "everflourish", "selflearning-switch:ef_r01", 11),
    ("EF raw r02 — S std R=2", "everflourish", "selflearning-switch:ef_r02", 11),
    ("EF raw r03 — S std R=3", "everflourish", "selflearning-switch:ef_r03", 11),
    ("EF raw r04 — S std R=4", "everflourish", "selflearning-switch:ef_r04", 11),
    ("EF raw r05 — S std R=5", "everflourish", "selflearning-switch:ef_r05", 11),
    ("EF raw r06 — S std R=6", "everflourish", "selflearning-switch:ef_r06", 11),
    ("EF raw r07 — S std R=7", "everflourish", "selflearning-switch:ef_r07", 11),
    ("EF raw r08 — S std R=8", "everflourish", "selflearning-switch:ef_r08", 11),
    ("EF raw r09 — S std R=9", "everflourish", "selflearning-switch:ef_r09", 11),
    ("EF raw r10 — S std R=10", "everflourish", "selflearning-switch:ef_r10", 11),
    ("EF raw r11 — S std R=15", "everflourish", "selflearning-switch:ef_r11", 11),
    ("EF raw r12 — S std R=20", "everflourish", "selflearning-switch:ef_r12", 11),
    # --- Group RT: Timing sweep — short/long pulse widths (all R=5) ---
    ("EF raw r13 — S short=30 long=57 R=5", "everflourish", "selflearning-switch:ef_r13", 11),
    ("EF raw r14 — S short=40 long=76 R=5", "everflourish", "selflearning-switch:ef_r14", 11),
    ("EF raw r15 — S short=50 long=95 R=5", "everflourish", "selflearning-switch:ef_r15", 11),
    ("EF raw r16 — S short=70 long=133 R=5", "everflourish", "selflearning-switch:ef_r16", 11),
    ("EF raw r17 — S short=80 long=152 R=5", "everflourish", "selflearning-switch:ef_r17", 11),
    ("EF raw r18 — S short=90 long=171 R=5", "everflourish", "selflearning-switch:ef_r18", 11),
    # --- Group RP: Preamble length sweep (all R=5) ---
    ("EF raw r19 — S preamble=0 R=5", "everflourish", "selflearning-switch:ef_r19", 11),
    ("EF raw r20 — S preamble=2 R=5", "everflourish", "selflearning-switch:ef_r20", 11),
    ("EF raw r21 — S preamble=4 R=5", "everflourish", "selflearning-switch:ef_r21", 11),
    ("EF raw r22 — S preamble=6 R=5", "everflourish", "selflearning-switch:ef_r22", 11),
    ("EF raw r23 — S preamble=10 R=5", "everflourish", "selflearning-switch:ef_r23", 11),
    ("EF raw r24 — S preamble=12 R=5", "everflourish", "selflearning-switch:ef_r24", 11),
    ("EF raw r25 — S preamble=16 R=5", "everflourish", "selflearning-switch:ef_r25", 11),
    # --- Group RD: Double/triple signal copies ---
    ("EF raw r26 — S×2 R=1", "everflourish", "selflearning-switch:ef_r26", 11),
    ("EF raw r27 — S×2 R=3", "everflourish", "selflearning-switch:ef_r27", 11),
    ("EF raw r28 — S×2 R=5", "everflourish", "selflearning-switch:ef_r28", 11),
    ("EF raw r29 — S×3 R=1", "everflourish", "selflearning-switch:ef_r29", 11),
    ("EF raw r30 — S×3 R=3", "everflourish", "selflearning-switch:ef_r30", 11),
    ("EF raw r31 — S×3 R=5", "everflourish", "selflearning-switch:ef_r31", 11),
    # --- Group RF: Frame/terminator combos ---
    ("EF raw r32 — S R=1 no+", "everflourish", "selflearning-switch:ef_r32", 11),
    ("EF raw r33 — S R=1 +term", "everflourish", "selflearning-switch:ef_r33", 11),
    ("EF raw r34 — S R=3 no+ P=0", "everflourish", "selflearning-switch:ef_r34", 11),
    ("EF raw r35 — S R=3 +term P=0", "everflourish", "selflearning-switch:ef_r35", 11),
    ("EF raw r36 — S R=3 +term P=5", "everflourish", "selflearning-switch:ef_r36", 11),
    ("EF raw r37 — S R=5 no+ P=0", "everflourish", "selflearning-switch:ef_r37", 11),
    ("EF raw r38 — S R=5 +term P=5", "everflourish", "selflearning-switch:ef_r38", 11),
    ("EF raw r39 — S R=5 +term P=37", "everflourish", "selflearning-switch:ef_r39", 11),
    ("EF raw r40 — S R=5 no+ P=37", "everflourish", "selflearning-switch:ef_r40", 11),
    # --- Group RI: Inverted bit encoding ---
    ("EF raw r41 — S inverted R=1", "everflourish", "selflearning-switch:ef_r41", 11),
    ("EF raw r42 — S inverted R=3", "everflourish", "selflearning-switch:ef_r42", 11),
    ("EF raw r43 — S inverted R=5", "everflourish", "selflearning-switch:ef_r43", 11),
    # --- Group RB: Bit order variations ---
    ("EF raw r44 — S MSB std R=5", "everflourish", "selflearning-switch:ef_r44", 11),
    ("EF raw r45 — S LSB reversed R=5", "everflourish", "selflearning-switch:ef_r45", 11),
    ("EF raw r46 — S LSB+inverted R=5", "everflourish", "selflearning-switch:ef_r46", 11),
    # --- Group RX: Cross timing combos ---
    ("EF raw r47 — S short=30 long=114 R=5", "everflourish", "selflearning-switch:ef_r47", 11),
    ("EF raw r48 — S short=60 long=57 R=5", "everflourish", "selflearning-switch:ef_r48", 11),
    ("EF raw r49 — S short=50 long=114 R=5", "everflourish", "selflearning-switch:ef_r49", 11),
    ("EF raw r50 — S short=60 long=95 R=5", "everflourish", "selflearning-switch:ef_r50", 11),
    ("EF raw r51 — S short=40 long=133 R=5", "everflourish", "selflearning-switch:ef_r51", 11),
    ("EF raw r52 — S short=80 long=114 R=5", "everflourish", "selflearning-switch:ef_r52", 11),
]

# ---- NATIVE (firmware protocol dict) test variants -----------------------
# Group NM: Model name variations
# Group NU: Unit offset variations (selflearning-switch)
# Group NU2: Unit offset variations (selflearning)
# Group NH: House offset variations
# Group NS: Native + S bytes hybrid
# Group NR: Native + R/P repeat values
# Group NC: Combo (native + S + R)
# Group NX: Extra / edge cases
_EF_TEST_NATIVE_VARIANTS: list[tuple[str, str, str, int]] = [
    # --- Group NM: Model name variations (unit offset 0) ---
    ("EF native n01 — model=selflearning-switch", "everflourish", "selflearning-switch:ef_n01", 11),
    ("EF native n02 — model=selflearning", "everflourish", "selflearning-switch:ef_n02", 11),
    ("EF native n03 — model=selflearning-dimmer", "everflourish", "selflearning-switch:ef_n03", 11),
    ("EF native n04 — model=switch", "everflourish", "selflearning-switch:ef_n04", 11),
    ("EF native n05 — model=everflourish", "everflourish", "selflearning-switch:ef_n05", 11),
    ("EF native n06 — model=codeswitch", "everflourish", "selflearning-switch:ef_n06", 11),
    ("EF native n07 — model=bell", "everflourish", "selflearning-switch:ef_n07", 11),
    # --- Group NU: Unit offsets (model=selflearning-switch) ---
    ("EF native n08 — sl-sw unit-3", "everflourish", "selflearning-switch:ef_n08", 11),
    ("EF native n09 — sl-sw unit-2", "everflourish", "selflearning-switch:ef_n09", 11),
    ("EF native n10 — sl-sw unit-1", "everflourish", "selflearning-switch:ef_n10", 11),
    ("EF native n11 — sl-sw unit+0", "everflourish", "selflearning-switch:ef_n11", 11),
    ("EF native n12 — sl-sw unit+1", "everflourish", "selflearning-switch:ef_n12", 11),
    ("EF native n13 — sl-sw unit+2", "everflourish", "selflearning-switch:ef_n13", 11),
    ("EF native n14 — sl-sw unit+3", "everflourish", "selflearning-switch:ef_n14", 11),
    # --- Group NU2: Unit offsets (model=selflearning) ---
    ("EF native n15 — sl unit-3", "everflourish", "selflearning-switch:ef_n15", 11),
    ("EF native n16 — sl unit-2", "everflourish", "selflearning-switch:ef_n16", 11),
    ("EF native n17 — sl unit-1", "everflourish", "selflearning-switch:ef_n17", 11),
    ("EF native n18 — sl unit+0", "everflourish", "selflearning-switch:ef_n18", 11),
    ("EF native n19 — sl unit+1", "everflourish", "selflearning-switch:ef_n19", 11),
    ("EF native n20 — sl unit+2", "everflourish", "selflearning-switch:ef_n20", 11),
    ("EF native n21 — sl unit+3", "everflourish", "selflearning-switch:ef_n21", 11),
    # --- Group NH: House offsets (model=selflearning-switch, unit+0) ---
    ("EF native n22 — house-2", "everflourish", "selflearning-switch:ef_n22", 11),
    ("EF native n23 — house-1", "everflourish", "selflearning-switch:ef_n23", 11),
    ("EF native n24 — house+0", "everflourish", "selflearning-switch:ef_n24", 11),
    ("EF native n25 — house+1", "everflourish", "selflearning-switch:ef_n25", 11),
    ("EF native n26 — house+2", "everflourish", "selflearning-switch:ef_n26", 11),
    # --- Group NS: Native + S bytes hybrid ---
    ("EF native n27 — sl-sw+S unit+0", "everflourish", "selflearning-switch:ef_n27", 11),
    ("EF native n28 — sl-sw+S unit-1", "everflourish", "selflearning-switch:ef_n28", 11),
    ("EF native n29 — sl+S unit+0", "everflourish", "selflearning-switch:ef_n29", 11),
    ("EF native n30 — sl+S unit-1", "everflourish", "selflearning-switch:ef_n30", 11),
    ("EF native n31 — sl-dimmer+S unit+0", "everflourish", "selflearning-switch:ef_n31", 11),
    ("EF native n32 — sl-dimmer+S unit-1", "everflourish", "selflearning-switch:ef_n32", 11),
    ("EF native n33 — switch+S unit+0", "everflourish", "selflearning-switch:ef_n33", 11),
    ("EF native n34 — codeswitch+S unit+0", "everflourish", "selflearning-switch:ef_n34", 11),
    # --- Group NR: Native + R/P repeat values ---
    ("EF native n35 — sl-sw R=1", "everflourish", "selflearning-switch:ef_n35", 11),
    ("EF native n36 — sl-sw R=3", "everflourish", "selflearning-switch:ef_n36", 11),
    ("EF native n37 — sl-sw R=5", "everflourish", "selflearning-switch:ef_n37", 11),
    ("EF native n38 — sl-sw R=10", "everflourish", "selflearning-switch:ef_n38", 11),
    ("EF native n39 — sl-sw R=1 P=5", "everflourish", "selflearning-switch:ef_n39", 11),
    ("EF native n40 — sl-sw R=3 P=5", "everflourish", "selflearning-switch:ef_n40", 11),
    ("EF native n41 — sl-sw R=5 P=5", "everflourish", "selflearning-switch:ef_n41", 11),
    ("EF native n42 — sl-sw R=10 P=5", "everflourish", "selflearning-switch:ef_n42", 11),
    # --- Group NC: Combo (native + S + R) ---
    ("EF native n43 — sl-sw+S+R=3 unit+0", "everflourish", "selflearning-switch:ef_n43", 11),
    ("EF native n44 — sl-sw+S+R=5 unit-1", "everflourish", "selflearning-switch:ef_n44", 11),
    ("EF native n45 — sl+S+R=5 unit+0", "everflourish", "selflearning-switch:ef_n45", 11),
    ("EF native n46 — sl+S+R=5 unit-1", "everflourish", "selflearning-switch:ef_n46", 11),
    ("EF native n47 — sl-dimmer+S+R=5 unit+0", "everflourish", "selflearning-switch:ef_n47", 11),
    ("EF native n48 — switch+S+R=3 unit+0", "everflourish", "selflearning-switch:ef_n48", 11),
    # --- Group NX: Edge cases ---
    ("EF native n49 — method as str 'turnon'", "everflourish", "selflearning-switch:ef_n49", 11),
    ("EF native n50 — method=1 (TURNON)", "everflourish", "selflearning-switch:ef_n50", 11),
    ("EF native n51 — method=2 (TURNOFF)", "everflourish", "selflearning-switch:ef_n51", 11),
    ("EF native n52 — method=16 (LEARN)", "everflourish", "selflearning-switch:ef_n52", 11),
    ("EF native n53 — method=0x80+int", "everflourish", "selflearning-switch:ef_n53", 11),
]

# Legacy alias (old 20 variants) — kept so existing devices still work
_EF_RAW_VARIANTS: list[tuple[str, str, str, int]] = [
    ("EF raw v1 — S-only bytes", "everflourish", "selflearning-switch:ef_v1", 11),
    ("EF raw v2 — S + R=4", "everflourish", "selflearning-switch:ef_v2", 11),
    ("EF raw v3 — S + R=10 P=5", "everflourish", "selflearning-switch:ef_v3", 11),
    ("EF raw v4 — S doubled", "everflourish", "selflearning-switch:ef_v4", 11),
    ("EF raw v5 — native nofix", "everflourish", "selflearning-switch:ef_v5", 11),
    ("EF raw v6 — native unit-1 fix", "everflourish", "selflearning-switch:ef_v6", 11),
    ("EF raw v7 — native model=selflearning nofix", "everflourish", "selflearning-switch:ef_v7", 11),
    ("EF raw v8 — native model=selflearning fix", "everflourish", "selflearning-switch:ef_v8", 11),
    ("EF raw v9 — native+S nofix", "everflourish", "selflearning-switch:ef_v9", 11),
    ("EF raw v10 — native+S fix", "everflourish", "selflearning-switch:ef_v10", 11),
    ("EF raw v11 — native+S+R+P nofix", "everflourish", "selflearning-switch:ef_v11", 11),
    ("EF raw v12 — native unit-2 fix", "everflourish", "selflearning-switch:ef_v12", 11),
    ("EF raw v13 — S half timing (300/570µs)", "everflourish", "selflearning-switch:ef_v13", 11),
    ("EF raw v14 — S double timing (1200/2280µs)", "everflourish", "selflearning-switch:ef_v14", 11),
    ("EF raw v15 — S inverted bits", "everflourish", "selflearning-switch:ef_v15", 11),
    ("EF raw v16 — S Duo sync prefix", "everflourish", "selflearning-switch:ef_v16", 11),
    ("EF raw v17 — S + R=5 (Duo repeat)", "everflourish", "selflearning-switch:ef_v17", 11),
    ("EF raw v18 — S + '+' terminator", "everflourish", "selflearning-switch:ef_v18", 11),
    ("EF raw v19 — S + R=5 P=37 '+' (full Duo)", "everflourish", "selflearning-switch:ef_v19", 11),
    ("EF raw v20 — native+S+R=5 fix", "everflourish", "selflearning-switch:ef_v20", 11),
]
PROTOCOL_RAW_CATALOG.extend(_EF_RAW_VARIANTS)
PROTOCOL_RAW_CATALOG.extend(_EF_TEST_RAW_VARIANTS)
PROTOCOL_RAW_CATALOG.extend(_EF_TEST_NATIVE_VARIANTS)

# ---------------------------------------------------------------------------
# EF test device — two separate test device flows:
#   1. RAW: 52 S-only pulse-train variants + 1 sequence button
#   2. NATIVE: 53 firmware dict variants + 1 sequence button
# ---------------------------------------------------------------------------

EF_TEST_RAW_VARIANTS: list[tuple[str, str]] = [
    (entry[2].split(":", 1)[1], entry[0])
    for entry in _EF_TEST_RAW_VARIANTS
]
EF_TEST_NATIVE_VARIANTS: list[tuple[str, str]] = [
    (entry[2].split(":", 1)[1], entry[0])
    for entry in _EF_TEST_NATIVE_VARIANTS
]
# Union of both for backward compat (button.py, tests, etc.)
EF_TEST_VARIANTS: list[tuple[str, str]] = (
    EF_TEST_RAW_VARIANTS + EF_TEST_NATIVE_VARIANTS
)
# Group UID prefix used to group all EF test entities under one HA device card.
EF_TEST_GROUP_UID = "ef_test"
# Default test house/unit (can be overridden in the flow).
EF_TEST_HOUSE = "100"
EF_TEST_UNIT = "1"

PROTOCOL_NATIVE_CATALOG: list[tuple[str, str, str, int]] = list(
    PROTOCOL_MODEL_CATALOG
)

PROTOCOL_RAW_MAP: dict[str, tuple[str, str, int]] = {
    label: (proto, model, widget)
    for label, proto, model, widget in PROTOCOL_RAW_CATALOG
}
PROTOCOL_RAW_LABELS: list[str] = [label for label, _, _, _ in PROTOCOL_RAW_CATALOG]

PROTOCOL_NATIVE_MAP: dict[str, tuple[str, str, int]] = {
    label: (proto, model, widget)
    for label, proto, model, widget in PROTOCOL_NATIVE_CATALOG
}
PROTOCOL_NATIVE_LABELS: list[str] = [label for label, _, _, _ in PROTOCOL_NATIVE_CATALOG]

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

