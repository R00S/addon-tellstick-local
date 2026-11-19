# issue-130-net-v1-dim — 3.4.1.x branch timeline

> Branch: `issue-130-net-v1-dim`. This file continues
> `docs/issue-130-net-v1-dim-3.4.0.x.md` after the Luxorparts two-path work
> (3.4.0.12–3.4.0.15) and starts the 3.4.1.x line with the add-flow rework.

## Session — 2026-11-19: add-flow sliders and duplicate warning (3.4.1.0)

### What the user asked for

* Sliders for house code and the other numeric parameters in **every** device
  add path, defaulting to the **next free** code.
* When the chosen combination would trigger a device that is already in the
  system, show a warning with the options to **change** or **proceed**.

### Changed

* `config_flow.py`:
  * `_build_params_schema()` now takes the stored devices, the protocol and the
    model. Every `int` field renders as an `int` `NumberSelector` in slider
    mode, letter houses (Nexa codeswitch A–P) render as a 1–N slider and are
    mapped back to the letter before storage, and the Luxorparts pair sliders
    start on the first pair no stored device of that path uses.
  * New `_next_free_params()` picks the first free `(house, unit)` combination
    of the same protocol from the stored devices (address first, then unit), so
    a new device never defaults onto an existing code. The old random seeding
    of self-learning houses is gone. Text code fields (sartano 10 digits,
    brateck 8 characters) cannot be sliders but still start on the next free
    code.
  * New `_used_rf_identities()` / `_conflicting_devices()` / `_rf_identity()`
    define the shared-signal rule: same protocol and same house + unit, vendor
    suffix after `:` ignored, sensors excluded.
  * `async_step_params()` coerces the slider values (`int(float(...))`, letter →
    `A`–`P`), resolves Luxorparts pairs, then checks for conflicts. A conflict
    stores the submitted values and shows `async_step_duplicate_warning()`;
    otherwise the previous confirm step runs unchanged.
  * New steps `duplicate_warning` (menu), `duplicate_change` (back to the
    parameter form, prefilled with the submitted values) and
    `duplicate_proceed` (pairs on the shared code). `_accept_params()` holds the
    shared "store parameters and go to confirm" body.
  * Every add path that asks for parameters (`by_brand`, `by_protocol`,
    `by_protocol_raw`, `by_protocol_native`, `by_protocol_native_nofix`) goes
    through this one step, so all of them get sliders and the warning. Discovery
    add and the Generic RF / Tuya recording flows take their values from the
    captured signal and have no house/unit form to slide.
* `strings.json` / `translations/en.json`: new `params` description, new
  `duplicate_warning`, `duplicate_change` and `duplicate_proceed` steps.
* `README.md`, `docs/USER_GUIDE.md` §5.2: sliders + first-free default + the
  duplicate warning and what "same code" means.
* Both manifests 3.4.0.15 → **3.4.1.0**.

### Verified

* `const.py` doctests, `py_compile`, pyflakes, `tests/test_ha_integration.py`.
* Byte-identical mirror, `strings.json` == `translations/en.json`.
* A script that builds the schemas from real stored devices and checks the
  next-free defaults, slider widgets, letter mapping and conflict detection.

### Not verified

* The forms in the Home Assistant UI (slider rendering, menu buttons) — no HA
  instance here.
* Any RF behaviour; the add flow sends the same codes as before for the same
  stored parameters.

## Session — 2026-11-19: "Add it anyway" creates a second device (3.4.1.1)

### What the user reported

Adding a device on a code another device already used, then choosing
**Add it anyway**, replaced the existing device instead of adding a second one
with the same codes (tested with an Anslut/comen device).

### Cause

Stored devices are keyed by `protocol_model_house_unit` (`build_device_uid()`).
The second device therefore reused the first device's key and wrote over its
entry in `CONF_DEVICES`, so only one device remained (the old entity was just
renamed).

### Changed

* `config_flow.py`: new `_unique_device_uid()` returns the plain key when it is
  free, otherwise the first free `_2`, `_3`… suffix. The confirm step builds the
  key with it, so **Add it anyway** stores a second device with the same
  house/unit — the stored RF codes, and therefore the transmitted signal, are
  unchanged. Editing a device's house/unit goes through the same helper with
  the device's own key ignored, so changing only the name of a shared-code
  device no longer moves it back onto the other device's key.
* `client.py`: `RawDeviceEvent.device_id` honours an explicit `_device_uid`
  parameter. The synthetic event that creates the entity right after pairing
  now carries the stored key, so the suffixed device gets its own entity instead
  of matching the existing one.
* `strings.json` / `translations/en.json`: the `duplicate_proceed` description
  says a separate device is added and the device already using the code is left
  untouched.
* `README.md`, `docs/USER_GUIDE.md` §5.2: same wording.
* Both manifests 3.4.1.0 → **3.4.1.1**.

### Verified

* `const.py` doctests, `py_compile`, pyflakes, `tests/test_ha_integration.py`.
* Byte-identical mirror, `strings.json` == `translations/en.json`.
* A harness against the real modules: a taken key gets `_2` then `_3`, a free
  key is unchanged, editing keeps its own key, and a synthetic event with
  `_device_uid` resolves to the suffixed key while a normal RF event still
  resolves to the base key.

### Not verified

* The Home Assistant UI end to end and any RF behaviour — no HA instance or
  TellStick hardware here.
