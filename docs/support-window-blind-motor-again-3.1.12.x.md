# Branch Timeline: support-window-blind-motor-again — 3.1.12.x

**Branch:** `copilot/support-window-blind-motor-again`
**Issue:** https://github.com/R00S/addon-tellstick-local/issues/100
**Started:** 2026-04-27

---

## Problem Statement

User reports a Kjell & Company window blind motor and asks if it can be
supported by TellStick Local.  The product is described as similar to the
[MOES Tuya WiFi Smart Curtain Motor Electric Chain Roller Blinds]
(https://www.banggood.com/MOES-Tuya-WiFi-Smart-Curtain-Motor-Electric-Chain-Roller-Blinds-…).

The user attached an rtl_433 log file captured with an RTL-SDR dongle:
`9b13b3f4_rtl433_2026-04-26T17-54-44.373Z.log`

---

## Signal Analysis (rtl_433 log)

The rtl_433 decoder output labels the device as `"model" : "kjell_blind"`.
This is NOT a standard rtl_433 built-in model name — it indicates a custom
flex decoder the user created for this device.

### Pulse timing (from rtl_433 Analyzing pulses section)

```
Pulse width distribution:
 [ 1] count: 26, width: ~772 us   ← long pulse
 [ 2] count: 23, width: ~368 us   ← short pulse

Gap width distribution:
 [ 1] count: 29, width: ~352 us   ← short gap
 [ 2] count: 23, width: ~760 us   ← long gap

Pulse period distribution:
 [ 1] count: 49, width: ~1124 us  ← fixed period
```

### Encoding interpretation

The fixed ~1124 µs period with two duty cycles suggests standard OOK/PWM:

| Bit | Pulse | Gap   | Period |
|-----|-------|-------|--------|
| "1" | 770µs | 360µs | 1130µs |
| "0" | 360µs | 760µs | 1120µs |

### Protocol comparison

| Protocol         | Short pulse | Long pulse | Period   | Match?     |
|------------------|-------------|------------|----------|------------|
| arctech SL       | ~240µs      | ~1270µs    | variable | ❌ No      |
| hasta v1         | ~170µs      | ~330µs     | ~500µs   | ❌ No      |
| hasta v2         | ~350µs      | ~630µs     | ~980µs   | ⚠️ Close   |
| Observed signal  | ~360µs      | ~770µs     | ~1124µs  |            |

The observed timing is closest to **hasta selflearningv2**, which has
T_short ≈ 35×10µs = 350µs and T_long ≈ 63×10µs = 630µs.  The slightly
longer period (~1124µs vs ~980µs) may be due to hardware variation or
a slightly different firmware timing parameter.

### Decoded data

Most decoded rows in the log are empty (`"len" : 0`), indicating the custom
flex decoder parameters do not fully match the signal.  A handful of entries
show 1 bit (`"len" : 1, "data" : "8"` or `"data" : "0"`), which is not
enough to identify the payload format.

**Conclusion:** The protocol is likely either a variant of `hasta selflearningv2`
or a fully proprietary Chinese OEM protocol not implemented in telldus-core.

---

## Implementation Decision

Since `hasta selflearningv2` is the closest known telldus-core protocol:

1. Added **"Kjell & Company — Blind motor"** to `DEVICE_CATALOG` in
   `const.py` (both the integration copy and the add-on bundle copy) using
   `hasta selflearningv2:kjelloco`, widget 16.

2. Updated `cover.py` docstrings to mention Kjell & Company as a supported
   brand via hasta selflearningv2.

**If this doesn't work on real hardware:**
- The motor might use a fully proprietary protocol not in telldus-core.
- The alternative is the "raw record/replay" approach (future feature) which
  bypasses protocol decoding entirely and replays the exact received waveform.
- The user could also try putting the motor in "learn" mode and pairing it
  with arctech selflearning commands — some generic RF motors accept any
  signal during their pairing sequence.

---

## Widget 16 — House and Unit for selflearningv2

Widget 16 is the parameter form for all `hasta` self-learning motors (Rollertrol, Hasta v2, and now Kjell & Company).  Its field definitions are:

```python
{"name": "house", "type": "int", "default": 1, "min": 1, "max": 65536, "random": True},
{"name": "unit", "type": "int", "default": 1, "min": 1, "max": 15},
```

`"random": True` means the "Add device" flow auto-generates a **random house code** (1–65536) every time a device is added.  There is no fixed house/unit — `selflearningv2` is a self-learning protocol, so the motor stores whatever code TellStick sends during pairing.

### Pairing procedure

1. HA: Settings → Devices & Services → TellStick Local → Configure → Add device → By brand → "Kjell & Company — Blind motor"
2. HA shows params form with a randomly generated house (e.g. `42573`) and unit `1`.
3. Press-and-hold the **learn/pair button on the motor** until the LED blinks (learn mode).
4. Click **Send learn signal** in HA → TellStick sends an RF LEARN frame with that house/unit.
5. Motor stores the code; UP/DOWN/STOP commands from HA now control it.

### Can we replicate the original remote's code?

In theory, if we could decode the original remote's house/unit from the rtl_433 log, TellStick could be paired to the same code so both the original remote AND HA control the motor simultaneously.  **In practice this is not currently possible:** the rtl_433 log shows all decoded rows as empty (`"len" : 0`) because the custom "kjell_blind" flex decoder does not successfully extract payload bits.

The practical approach is to pair the motor fresh with TellStick's generated code.

---

## Changes Made

| File | Change |
|------|--------|
| `custom_components/tellstick_local/const.py` | Added "Kjell & Company — Blind motor" to DEVICE_CATALOG |
| `custom_components/tellstick_local/cover.py` | Updated docstring |
| `custom_components/tellstick_local/manifest.json` | Version bump 3.1.12.15 → 3.1.12.16 |
| `tellsticklive/rootfs/usr/share/tellstick_local/const.py` | Added "Kjell & Company — Blind motor" to DEVICE_CATALOG |
| `tellsticklive/rootfs/usr/share/tellstick_local/cover.py` | Updated docstring |
| `tellsticklive/rootfs/usr/share/tellstick_local/manifest.json` | Version bump 3.1.12.15 → 3.1.12.16 |
| `docs/support-window-blind-motor-again-3.1.12.x.md` | This file |
