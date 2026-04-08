# Removed EF Test Paths — How to Restore

The EF (Everflourish) test paths were removed from the "Add device" menu
in v3.1.9.0 to clean up the user-facing interface for the stable release.
All the underlying code still exists (EF_TEST constants, EF sequence
buttons in `button.py`).

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
