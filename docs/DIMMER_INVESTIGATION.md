# Arctech Selflearning Dimmer — Investigation Log

**Branch:** `copilot/retrieve-rtl-conf-luxorparts`
**Issue:** https://github.com/R00S/addon-tellstick-local/issues/90
**Started:** 2026-04-17

---

## Summary of symptoms

| Backend | Symptom |
|---------|---------|
| **Duo** | User (skallberg) reports dimmer entity IS created (TellStickLight appears) but dim commands are **not received by the physical device** |
| **Duo** | R00S reports: freshly-added Proove selflearning dimmer shows **only on/off and learn entities** — no brightness slider visible |
| **ZNet** | R00S: same "only on/off and learn entities" for Proove selflearning dimmer added by brand |

---

## RTL-SDR captures (from issue comment, 2026-04-17)

R00S used a real RTL-SDR dongle to capture what Telldus Live sends for the Nexa/Proove selflearning dimmer. The captured device was **house=278019, unit=1**.

### Decoded frame structure (arctech selflearning DIM)

Protocol: OOK-PPM, s=220µs, l=1260µs, reset=2548µs  
72 gap values = 36 data symbols = DIM frame format (not the normal 32-bit TURNON/TURNOFF)

```
[house 26 bits] [group 1 bit] [DIM indicator] [unit 4 bits] [level 4 bits]
```

The DIM indicator is two SHORT-SHORT gap pairs instead of a SHORT-LONG or LONG-SHORT pair.

### 4 captured DIM frames (from pulse_slicer_ppm device codes)

| Hex payload (72 bits) | Level field | ≈% |
|---|---|---|
| `555655aa9555a45565` | `0100` = 4 | ~25% |
| `555655aa9555a45595` | `1000` = 8 | ~50% |
| `555655aa9555a455a5` | `1100` = 12 | ~75% |
| `555655aa9555a455aa` | `1111` = 15 | ~100% |

The house code `278019` decodes cleanly:  
`0000 0001 0000 1111 1000 0000 11` (binary, 26 bits MSB-first) = 262144 + 8192 + 4096 + 2048 + 1024 + 512 + 2 + 1 = **278019** ✓

OFF (the 5th level Telldus Live shows) sends a standard **TURNOFF** frame (64 gap values / 32 bits), not a DIM frame. No TURNOFF capture in the issue but this is the well-known arctech format.

### Level mapping (HA brightness 0-255 → hw level 0-15)

`hw_level = ha_brightness // 16`

| HA brightness | hw level | % |
|---|---|---|
| 64 | 4 | ~25% |
| 128 | 8 | ~50% |
| 192 | 12 | ~75% |
| 255 | 15 | ~100% |

---

## Code analysis

### Entity type creation path

When a user adds a Proove selflearning dimmer via **Options → Add device → By brand**:

1. `async_step_by_brand` sets `CONF_DEVICE_MODEL = "selflearning-dimmer:proove"` from `DEVICE_CATALOG`.
2. `async_step_confirm` (Duo path):
   - Calls `controller.add_device(name, "arctech", "selflearning-dimmer:proove", params)`
   - `client.py::add_device()` strips vendor suffix → registers `"selflearning-dimmer"` with telldusd ✓
   - Gets back integer `telldusd_id`
   - Stores in `device_id_map[device_uid] = telldusd_id`
   - Persists `CONF_DEVICE_MODEL = "selflearning-dimmer:proove"` in `entry.options`
   - Dispatches synthetic `RawDeviceEvent` with:
     - `model = "selflearning"` (RF-normalized)
     - `_catalog_model = "selflearning-dimmer:proove"` (in raw string params)
3. `switch.py::_async_new_device` fires:
   - `check_model = "selflearning-dimmer:proove"` (from `_catalog_model`)
   - `_is_switch("arctech", "selflearning-dimmer:proove")` → `base = "selflearning-dimmer"` → **NOT in `_SWITCH_MODELS`** → returns early, no switch created ✓
4. `light.py::_async_new_device` fires:
   - `check_model = "selflearning-dimmer:proove"` (from `_catalog_model`)
   - `_is_dimmer("arctech", "selflearning-dimmer:proove")` → `base = "selflearning-dimmer"` → **in `_DIMMER_MODELS`** → creates `TellStickLight` ✓
   - `TellStickLight` has `ColorMode.BRIGHTNESS` → HA should show brightness slider

**Conclusion from code analysis:** The code path looks correct. `TellStickLight` with `ColorMode.BRIGHTNESS` should be created. The slider should appear in HA when you click the entity detail card.

### Possible cause of "no slider visible" (R00S's report)

**Most likely:** The entity IS a `TellStickLight` (light entity), but in HA's entity list it shows only an on/off toggle. The brightness slider only appears when you **click on the entity card** to open the detail view. Telldus Live shows 5 preset buttons inline — HA hides the slider in the detail popup.

**Alternative:** There is a currently-unknown code path that creates a TellStickSwitch instead. This could happen if `_catalog_model` is missing from the event params in some edge case.

### Dim command path for Duo

`light.py::async_turn_on(brightness=X)`:
```python
await self._controller.dim(self._telldusd_device_id, level)
```
→ `client.py::dim(device_id, level)`:
```python
await self._send_command("tdDim", [_encode_int(device_id), _encode_int(level)])
```
→ telldusd `tdDim(id, level)` → arctech `stringSelflearningForCode(DIM, level)` → `hw_level = level // 16` → RF DIM frame

This **should work correctly** for the Duo if `_telldusd_device_id` is non-None.

**Possible cause of "not sending dim commands" (skallberg's report):**
- `self._telldusd_device_id` could be `None` if `device_id_map.get(uid)` returns nothing due to a UID mismatch
- OR: the slider exists but the entity always snaps back to 100% making it appear non-functional

### Dim command path for ZNet

`net_client.py::dim(device_dict, level)` → `_send_rf(device, "dim", param=level)` → `_encode_arctech_command(model, house, unit, "dim", level)`:

```python
if method_int == _DIM:
    return OrderedDict(
        protocol="arctech",
        model="selflearning-dimmer",
        house=house_val,
        unit=unit0,
        method=_TURNON,   # ← always TURNON regardless of level!
    )
```

The ZNet firmware's `handleSend()` always passes `None` as the level to `stringForMethod()`. Sending `_DIM` with any level → crashes at `None / 16`. The only working workaround is TURNON with `selflearning-dimmer`, which the firmware converts to `DIM(255)` = **full brightness only**.

**ZNet limitation: variable-level dimming is fundamentally impossible via the UDP interface.**

### `_arctech_dim_pulse_train` function (net_client.py line 1134)

This function generates the correct raw S bytes for any arctech selflearning DIM level. The RTL-SDR captures confirm the encoding is correct (`level // 16` maps HA 0-255 to hw 0-15). **But:** the comment says this function is unused because ZNet's `handleSend()` drops pure S-byte packets (crashes at `msg['protocol']` KeyError before reaching the RF chip queue). The function is kept for reference.

---

## What has been tried / verified

| Attempt | Result |
|---|---|
| Raw S-bytes only (no protocol key) in ZNet UDP | ❌ Crashes at `msg['protocol']` KeyError — RF never queued |
| S-bytes + protocol/model/house/unit + method=_DIM | ❌ Crashes at `level / 16` (level is always None) — RF never queued |
| TURNON + model="selflearning-dimmer" | ✓ Works on ZNet — but always DIM(255) = 100% |
| `tdDim(id, level)` on Duo | ✓ Should work per code analysis — **NOT yet confirmed by hardware test** |
| Entity type routing (switch vs light) | ✓ Code logic correct for manually-added devices (catalog_model path) |

---

## Known issues still open

1. **"No slider visible" (Duo/ZNet, R00S):** Need to confirm whether the entity is actually a `light.*` or `switch.*` entity. Check entity_id prefix in HA.
   - If `light.*` → UX confusion: user needs to click entity to see slider
   - If `switch.*` → there is a bug in the entity creation path not yet identified

2. **"Dim commands not sent to device" (Duo, skallberg):** Need to check:
   - Is `_telldusd_device_id` non-None? (UID mismatch would make it None)
   - Does the Duo LED blink when dimming via HA slider?
   - Check HA logs for "Cannot send" warnings from `light.py`

3. **ZNet variable dim:** Fundamentally impossible with current firmware. Options:
   - Accept 100%-only limitation and document it
   - Implement 5 preset level buttons as additional HA entities (button.py)
   - Wait for ZNet firmware with `tdSendRawCommand` or raw UDP path

---

## Next steps to confirm/fix

1. **R00S tests:** After adding dimmer via "Add device", go to HA entity list for the device. Check if entity has `light.` prefix (not `switch.`). Then click the entity to see if brightness slider appears.

2. **UID mismatch check (skallberg):** Enable debug logging for `custom_components.tellstick_local` and check for "Cannot send on command" or "no telldusd device ID" warnings when trying to dim.

3. **Duo hardware test:** Add a Proove selflearning dimmer via integration, click entity, move slider to 50%. Watch TellStick LED — it should blink (sends RF). If no blink → telldusd not receiving the command.

4. **ZNet preset buttons (future):** Implement 4 `button.*` entities per dimmer device with preset levels 25/50/75/100% as an alternative to the broken variable slider.

---

## Relevant files

| File | What to look at |
|---|---|
| `custom_components/tellstick_local/light.py` | `TellStickLight`, `_is_dimmer()`, `async_turn_on()` |
| `custom_components/tellstick_local/switch.py` | `_is_switch()`, `_SWITCH_MODELS` |
| `custom_components/tellstick_local/client.py` | `dim()`, `add_device()` |
| `custom_components/tellstick_local/net_client.py` | `_encode_arctech_command()`, `_arctech_dim_pulse_train()` |
| `custom_components/tellstick_local/config_flow.py` | `async_step_confirm()` — synthetic event construction |
| `custom_components/tellstick_local/const.py` | `DEVICE_CATALOG`, `normalize_rf_model()`, `build_device_uid()` |
