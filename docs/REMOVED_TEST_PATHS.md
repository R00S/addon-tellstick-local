# Removed Test Paths — How to Restore

These GUI test paths were removed from the "Add device" menu in v3.1.9.0
to clean up the user-facing interface for the stable release.  All the
underlying code still exists (EF_TEST constants, EF sequence buttons in
`button.py`, Luxorparts raw encoding in `const.py`).

This document records everything needed to put them back.

---

## 1. EF Test Paths (Everflourish encoding variants)

### What they did

Two separate flows that bulk-created switch entities for every Everflourish
encoding variant so the user could press each one and watch the TellStick
LED to find the working variant.

- **`ef_test_raw`** — Raw S-only pulse variants (bypasses ZNet firmware)
- **`ef_test_native`** — Native firmware dict variants (through ZNet protocol stack)

Each flow created N switch entities + 1 "sequence ALL" button that fired
all variants in order with 2-second delays.

### Where to re-add menu entries

In `config_flow.py`, method `async_step_user()`:

```python
# Net/ZNet menu — add ef_test_raw and ef_test_native back:
if backend == BACKEND_NET:
    return self.async_show_menu(
        step_id="user",
        menu_options=["by_brand", "by_protocol_raw", "by_protocol_native",
                       "by_protocol_native_nofix",
                       "ef_test_raw", "ef_test_native"],
    )
```

### Imports needed in `config_flow.py`

```python
from .const import (
    EF_TEST_HOUSE,
    EF_TEST_NATIVE_VARIANTS,
    EF_TEST_RAW_VARIANTS,
    EF_TEST_UNIT,
    # ... existing imports ...
)
```

### Flow methods to restore in `config_flow.py`

Add these methods back to `TellStickLocalAddDeviceFlow`:

```python
# ------------------------------------------------------------------
# EF test devices — two separate flows for raw vs native variants
# ------------------------------------------------------------------

async def _async_ef_test_create(
    self,
    user_input: dict[str, Any] | None,
    variants: list[tuple[str, str]],
    group_prefix: str,
    seq_model: str,
    step_id: str,
) -> SubentryFlowResult:
    """Shared helper for EF test raw/native flows.

    Creates one switch entity per variant + one sequence button,
    persists to options, reloads the integration entry, and reports
    progress.
    """
    errors: dict[str, str] = {}

    if user_input is not None:
        house = str(user_input.get("house", EF_TEST_HOUSE))
        unit = str(user_input.get("unit", EF_TEST_UNIT))

        entry = self._get_entry()
        entry_data = self.hass.data[DOMAIN].get(entry.entry_id, {})
        device_id_map: dict[str, Any] = entry_data.get(
            ENTRY_DEVICE_ID_MAP, {}
        )

        existing_devices = dict(entry.options.get(CONF_DEVICES, {}))
        group_uid = f"{group_prefix}_{house}_{unit}"
        created = 0

        # --- Create one switch entity per variant ---
        for variant_suffix, label in variants:
            model = f"selflearning-switch:{variant_suffix}"
            device_uid = f"ef_test_{variant_suffix}_{house}_{unit}"
            if device_uid in existing_devices:
                continue

            device_dict: dict[str, Any] = {
                CONF_DEVICE_PROTOCOL: "everflourish",
                CONF_DEVICE_MODEL: model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
                CONF_DEVICE_ENCODING: "",
            }
            device_id_map[device_uid] = device_dict

            existing_devices[device_uid] = {
                CONF_DEVICE_NAME: label,
                CONF_DEVICE_PROTOCOL: "everflourish",
                CONF_DEVICE_MODEL: model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
                CONF_DEVICE_ENCODING: "",
                "group_uid": group_uid,
            }
            created += 1

        # --- Create the "sequence all" marker device ---
        seq_uid = f"ef_test_{group_prefix}_seq_{house}_{unit}"
        if seq_uid not in existing_devices:
            existing_devices[seq_uid] = {
                CONF_DEVICE_NAME: f"EF test {group_prefix} — sequence ALL (h={house} u={unit})",
                CONF_DEVICE_PROTOCOL: "everflourish",
                CONF_DEVICE_MODEL: seq_model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
                CONF_DEVICE_ENCODING: "",
                "group_uid": group_uid,
            }
            created += 1

        # Persist everything
        new_options = dict(entry.options)
        new_options[CONF_DEVICES] = existing_devices
        self.hass.config_entries.async_update_entry(
            entry, options=new_options
        )

        _LOGGER.info(
            "EF test %s: created %d entities (house=%s unit=%s), reloading",
            group_prefix, created, house, unit,
        )

        # Reload the integration entry so new entities appear immediately
        await self.hass.config_entries.async_reload(entry.entry_id)

        return self.async_abort(reason="device_added")

    return self.async_show_form(
        step_id=step_id,
        data_schema=vol.Schema(
            {
                vol.Required("house", default=int(EF_TEST_HOUSE)): vol.All(
                    int, vol.Range(min=0, max=16383),
                ),
                vol.Required("unit", default=int(EF_TEST_UNIT)): vol.All(
                    int, vol.Range(min=1, max=4),
                ),
            }
        ),
        description_placeholders={"count": str(len(variants))},
        errors=errors,
    )

async def async_step_ef_test_raw(
    self, user_input: dict[str, Any] | None = None
) -> SubentryFlowResult:
    """Add all EF raw (S-only) pulse encoding test variants."""
    return await self._async_ef_test_create(
        user_input,
        variants=EF_TEST_RAW_VARIANTS,
        group_prefix="ef_test_raw",
        seq_model="ef_test_raw_sequence",
        step_id="ef_test_raw",
    )

async def async_step_ef_test_native(
    self, user_input: dict[str, Any] | None = None
) -> SubentryFlowResult:
    """Add all EF native (firmware dict) encoding test variants."""
    return await self._async_ef_test_create(
        user_input,
        variants=EF_TEST_NATIVE_VARIANTS,
        group_prefix="ef_test_native",
        seq_model="ef_test_native_sequence",
        step_id="ef_test_native",
    )
```

### Strings/translations for EF test flows

These keys already exist in `strings.json` and `translations/en.json`
(they were NOT removed — only the menu entries were removed):

```json
"ef_test_raw": "⚡ Add EF test — RAW (S-only pulse variants)",
"ef_test_native": "⚡ Add EF test — NATIVE (firmware dict variants)",
```

Step descriptions:

```json
"ef_test_raw": {
  "title": "Add EF test device — RAW pulse variants",
  "description": "Creates **{count} switch entities** + **1 sequence button** for raw S-only pulse encoding tests.\n\nThese variants send raw pulse-train bytes directly — this is the path that makes the TellStick ZNet LED blink.\n\nVariations include: timing sweeps, repeat counts, preamble lengths, signal copies, terminators, inverted bits."
},
"ef_test_native": {
  "title": "Add EF test device — NATIVE firmware variants",
  "description": "Creates **{count} switch entities** + **1 sequence button** for native firmware dict encoding tests.\n\nThese variants send protocol dicts through the ZNet firmware's protocol handler. Testing confirms these currently do NOT make the ZNet LED blink — this device is for exhaustive testing of the native path.\n\nVariations include: model names, unit/house offsets, S+native combos, R/P values."
}
```

### Constants still in `const.py` (NOT removed)

- `EF_TEST_HOUSE = "100"`
- `EF_TEST_UNIT = "1"`
- `EF_TEST_RAW_VARIANTS` — list of `(suffix, label)` tuples
- `EF_TEST_NATIVE_VARIANTS` — list of `(suffix, label)` tuples
- `EF_TEST_VARIANTS = EF_TEST_RAW_VARIANTS + EF_TEST_NATIVE_VARIANTS`
- `_EF_TEST_RAW_VARIANTS` — list of `(label, protocol, model, widget)` tuples
- `_EF_TEST_NATIVE_VARIANTS` — same format

### Sequence button in `button.py` (NOT removed)

The `_SEQ_MODELS` dict in `button.py` still has the EF test sequence
models (`ef_test_sequence`, `ef_test_raw_sequence`, `ef_test_native_sequence`).
The `EFTestSequenceButton` class is still present.

---

## 2. LX Test Path (Luxorparts bulk LPD entity creator)

### What it did

A single flow that bulk-created one switch entity per LPD code (up to 31
entities at v3.1.8.x, now 24 after removing remote pairs).  Used for
testing which LPD code works with a given receiver.

### Removed from `const.py`

```python
_LX_TEST_VARIANTS: list[tuple[str, str, str, int]] = [
    (f"LPD {lpd} — {src} {orig}",
     "luxorparts", "selflearning-switch:lx_live", 11)
    for lpd, _on, _off, src, orig in LX_LPD_LIST
]

# Add LX test variants to the raw protocol catalog for visibility
PROTOCOL_RAW_CATALOG.extend(_LX_TEST_VARIANTS)

# Each LPD entity: (variant_suffix, label, house, unit) for config_flow.
# house = LPD number (string), unit = "1".
LX_LPD_ENTITIES: list[tuple[str, str, str, str]] = [
    (f"lx_lpd{lpd}", f"LPD {lpd} — {src} {orig}",
     str(lpd), "1")
    for lpd, _on, _off, src, orig in LX_LPD_LIST
]

# (variant_suffix, label) pairs for the sequence-ALL button in button.py.
# Derived from LX_LPD_ENTITIES — same order, same labels.
LX_TEST_VARIANTS: list[tuple[str, str]] = [
    (suffix, label) for suffix, label, _h, _u in LX_LPD_ENTITIES
]

LX_TEST_GROUP_UID = "lx_test"
```

### Removed from `config_flow.py`

Import:
```python
from .const import LX_LPD_ENTITIES
```

Menu entry:
```python
# In async_step_user(), add "lx_test" to both Net and Duo menus:
menu_options=["by_brand", "by_protocol", "lx_test"],  # Duo
menu_options=["by_brand", ..., "lx_test"],             # Net
```

Flow methods:
```python
async def _async_lx_test_create(
    self,
    user_input: dict[str, Any] | None,
    lpd_entities: list[tuple[str, str, str, str]],
    group_prefix: str,
    seq_model: str,
    step_id: str,
) -> SubentryFlowResult:
    """Create Luxorparts LPD test entities.

    Each LPD code gets its own entity with a synthetic house/unit
    that maps to the exact ON/OFF codes in LX_GROUND_TRUTH_CODES.
    No house/unit form — codes are hardcoded from RTL-433 captures.
    """
    if user_input is not None:
        entry = self._get_entry()
        entry_data = self.hass.data[DOMAIN].get(entry.entry_id, {})
        device_id_map: dict[str, Any] = entry_data.get(
            ENTRY_DEVICE_ID_MAP, {}
        )

        existing_devices = dict(entry.options.get(CONF_DEVICES, {}))
        created = 0

        # --- Create one switch entity per LPD code ---
        for variant_suffix, label, house, unit in lpd_entities:
            model = "selflearning-switch:lx_live"
            device_uid = f"lx_test_{variant_suffix}"
            if device_uid in existing_devices:
                continue

            device_dict: dict[str, Any] = {
                CONF_DEVICE_PROTOCOL: "luxorparts",
                CONF_DEVICE_MODEL: model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
                CONF_DEVICE_ENCODING: "",
            }
            device_id_map[device_uid] = device_dict

            existing_devices[device_uid] = {
                CONF_DEVICE_NAME: label,
                CONF_DEVICE_PROTOCOL: "luxorparts",
                CONF_DEVICE_MODEL: model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
                CONF_DEVICE_ENCODING: "",
            }
            created += 1

        # Persist everything
        new_options = dict(entry.options)
        new_options[CONF_DEVICES] = existing_devices
        self.hass.config_entries.async_update_entry(
            entry, options=new_options
        )

        _LOGGER.info(
            "LX test %s: created %d LPD entities, reloading",
            group_prefix, created,
        )

        # Reload the integration entry so new entities appear immediately
        await self.hass.config_entries.async_reload(entry.entry_id)

        return self.async_abort(reason="device_added")

    return self.async_show_form(
        step_id=step_id,
        data_schema=vol.Schema({}),
        description_placeholders={"count": str(len(lpd_entities))},
    )

async def async_step_lx_test(
    self, user_input: dict[str, Any] | None = None
) -> SubentryFlowResult:
    """Add all Luxorparts LPD test entities."""
    return await self._async_lx_test_create(
        user_input,
        lpd_entities=LX_LPD_ENTITIES,
        group_prefix="lx_test",
        seq_model="lx_test_sequence",
        step_id="lx_test",
    )
```

### Removed from `button.py`

Import:
```python
from .const import LX_TEST_VARIANTS
```

Sequence model entry:
```python
# Add this back to _SEQ_MODELS in button.py:
"lx_test_sequence": (LX_TEST_VARIANTS, "lx_test_sequence", "luxorparts", "lx_test"),
```

### Strings/translations for LX test flow

```json
"lx_test": "🔌 Add Luxorparts switch (50969/50970/50972)"
```

Step description:
```json
"lx_test": {
  "title": "Add Luxorparts switch",
  "description": "Creates a switch entity for a **Luxorparts 50969/50970/50972** receiver.\n\nPick a **house code** (1–65535) and **unit** (1–8). Each combination generates unique ON/OFF signals.\n\n**To teach the receiver:** put it in learn mode (hold button until LED flashes), then press **ON** in HA."
}
```

Button entity translation:
```json
"lx_test_sequence": {
  "name": "Test ALL LX variants (sequence)"
}
```

---

## 3. by_protocol_raw Path (Net/ZNet raw pulse protocol picker)

### What it did

A protocol picker showing all protocols that have raw pulse-train encoders.
These bypass ZNet firmware bugs by sending raw S-data directly.

### Where to re-add

In `config_flow.py`, method `async_step_user()`:

```python
# Net/ZNet menu — add "by_protocol_raw" back:
menu_options=["by_brand", "by_protocol_raw", "by_protocol_native", "by_protocol_native_nofix"],
```

### Flow method (NOT removed — still in code)

`async_step_by_protocol_raw()` is still in `config_flow.py`.
Only the menu entry was removed.

### String (NOT removed):

```json
"by_protocol_raw": "Add by protocol (raw pulse)"
```

---

## 4. Removed Remote LPD Pairs

These physical-remote-sniffed pairs were removed from `LX_LPD_LIST` because
they don't work reliably with TellStick hardware:

```python
# --- Physical Remotes (Remote 1 ch D excluded — no ON code) ---
(25, 0xAEBEEA8, 0xAEBEEB8, "Remote", "R1-A"),
(26, 0xAEBAEB8, 0xAEBBEA8, "Remote", "R1-B"),
(27, 0xAEAFEB8, 0xAEBAEA8, "Remote", "R1-C"),
(28, 0xAFBEEA8, 0xAFBEEB8, "Remote", "R2-A"),
(29, 0xAFBBEA8, 0xAFBBEB8, "Remote", "R2-B"),
(30, 0xAFBAEA8, 0xAFBAEB8, "Remote", "R2-C"),
(31, 0xAFAFEA8, 0xAFAFEB8, "Remote", "R2-D"),
```

To restore: append to `LX_LPD_LIST` in `const.py` (after the last Live
pair), and update `LX_LPD_LIST` type hint count comment.

---

## 5. Luxorparts learn-via-ON change

The original learn function in `button.py` (`_send_luxorparts_learn`) used
`luxorparts_learn_commands()` which sends the ON code with R=50 repeats
(50 × single packet via P\x02 R<n> S<data>+).  This was replaced with a
single `luxorparts_build_raw_command()` call (R=10 repeats, same as ON).

**Reason:** R=50 does NOT flash the Duo hardware. R=10 (ON command) works,
and the receiver learns any valid code during learn mode.

To restore the original high-repeat learn:

```python
# Import in button.py:
from .const import luxorparts_learn_commands

# In _send_luxorparts_learn:
commands = luxorparts_learn_commands(code, total_repeats=50, variant=variant)
for i, raw_cmd in enumerate(commands):
    result = await controller.send_raw_command(raw_cmd)
    # ... handle result ...
    if i < len(commands) - 1:
        await asyncio.sleep(0.5)
```

`luxorparts_learn_commands()` is still in `const.py` (NOT removed).

---

## Reference commit

All removals were made in commit `b552c44` on branch
`copilot/implement-luxorparts-rf-protocol`.  Use `git show b552c44` or
`git diff b552c44~1 b552c44` to see the exact diff.
