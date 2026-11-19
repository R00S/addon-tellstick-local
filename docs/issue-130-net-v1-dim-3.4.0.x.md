# issue-130-net-v1-dim — 3.4.0.x branch timeline

> Branch: `issue-130-net-v1-dim`. This file continues
> `docs/issue-130-net-v1-dim-3.3.3.x.md` after the branch merged
> `net-v1-protocols` and joined the 3.4.0.x line.

## Session — 2026-11-19: test device reshaped, LX-T1 rejected by hardware

### What the user reported

* The dev-channel test release did not contain the requested device: it was
  five separately added devices, each with its own code picker and pairing
  step. The requirement is **one device with five on/off switches**, with no
  learning step — a Luxorparts receiver learns from the ON code it hears.
* The lowest code (LX-T1, `0xAEABEA8` / `0xAEABEB8`) was offered to a 50969 in
  learn mode and was **not** accepted.

### Changed

* `const.py`: the catalog entry is now **"Luxorparts — Test device, 5 switches
  (beta, Duo only)"**; widget 21 no longer asks for a house code 101–105
  because the dedicated step creates all five itself.
* `config_flow.py`: new `async_step_lx_test()`. `async_step_by_brand()` routes
  widget 21 there instead of the params/confirm steps. It writes the five device
  configs in one pass with `group_uid` = the name given one step earlier, so Home Assistant
  shows **one** device holding LX-T1…LX-T5, and dispatches one synthetic event
  per switch. Nothing is transmitted — there is no learn signal and no confirm
  step.
* Each of the five configs carries `no_learn_button`; `button.py` skips the
  Learn button for those devices, both when pre-creating stored devices and on
  the new-device signal.
* `strings.json` / `translations/en.json`: `lx_test` step text (explains that no
  pairing signal is sent) and the `lx_test_added` abort text.
* Docs: README, `docs/USER_GUIDE.md` §5.2 and §15,
  `docs/LUXORPARTS_PAIRS.md`, `docs/LUXORPARTS_TIMELINE.md` and
  `docs/LUXORPARTS_PROTOCOL_ANALYSIS.md` §7/§9 now describe the single-device
  form, the ON-code pairing and the LX-T1 result.

### Version

3.4.0.3 → **3.4.0.4** in both `manifest.json` files, so the reshaped test
device is distinguishable from the `3.4.0.3.20261119110747` dev build.

### Verification

* `tests/test_ha_integration.py`, `py_compile`, the `const.py` doctests, and a
  script assertion that the five test configs get five distinct UIDs sharing one
  `group_uid`.
* Mirror copies under `tellsticklive/rootfs/` are byte-identical.

### Not verified

* No Luxorparts receiver here. On the user's hardware LX-T1 was rejected;
  LX-T2…LX-T5 differ only in the button-field bits and remain untested, so
  scheme A is still unproven.
* The five-switch grouping has not been looked at in a running Home Assistant —
  only the config data it produces was checked.
