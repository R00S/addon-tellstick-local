# Branch: fix-config-flows-user-guide-links — 3.3.1.x

## Problem

Even after the previous fix (PR #106 — `fix-question-marks-in-readme`), user
reports that:

1. **Most config flows are still missing the ? user guide link** — the
   HA-generated hub-picker dialog ("Add 433 MHz device") has no ? because it is
   rendered entirely by HA, not by the integration.

2. **Where ? links exist, they lead to the repo page** — the manifest
   `documentation` field was still pointing to the repo root
   (`https://github.com/R00S/addon-tellstick-local`). HA uses this as the
   fallback ? URL for any dialog that doesn't have a step-level
   `description_url`. It is also the link shown in the HA integration info
   panel and in HACS.

3. **One broken anchor** — the mirror/range-extender `description_url` used
   `#8-mirror--range-extender` (double hyphen) but the actual GitHub anchor
   for `## 8. Mirror / range extender` is `#8-mirror-range-extender` (single
   hyphen, because `/` is removed, collapsing the surrounding spaces).

4. **`options.step.init` has no title** — the first screen of the options flow
   is a plain menu with a `description_url` but no `title`, making the ? button
   placement ambiguous in HA's UI.

## Root Causes

- `manifest.json` → `documentation` pointing to repo root rather than
  `docs/USER_GUIDE.md`.
- GitHub anchor generation: `##  8. Mirror / range extender` → the `/` is
  stripped, spaces collapse → single hyphen, not double.
- `options.step.init` missing `title` field.

## Fix

1. **Manifest** (`custom_components/tellstick_local/manifest.json` and
   `tellsticklive/rootfs/usr/share/tellstick_local/manifest.json`): change
   `documentation` to
   `https://github.com/R00S/addon-tellstick-local/blob/main/docs/USER_GUIDE.md`.

2. **Broken anchor** (all 4 strings/translations files): change
   `#8-mirror--range-extender` → `#8-mirror-range-extender`.

3. **options.init title** (all 4 strings/translations files): add
   `"title": "TellStick Local"` to `options.step.init`.

4. **Version bump**: `3.3.0.2` → `3.3.1.0` (new branch, bump C, reset D).

## Files to update

- `custom_components/tellstick_local/manifest.json`
- `tellsticklive/rootfs/usr/share/tellstick_local/manifest.json`
- `custom_components/tellstick_local/strings.json`
- `custom_components/tellstick_local/translations/en.json`
- `tellsticklive/rootfs/usr/share/tellstick_local/strings.json`
- `tellsticklive/rootfs/usr/share/tellstick_local/translations/en.json`

## Note on hub-picker dialog

The "Add 433 MHz device" dialog that shows a list of hubs is generated
entirely by the HA framework when there are multiple config entries. The
integration cannot inject a `description_url` into it. Fixing the manifest
`documentation` URL means the HA integration-info page and HACS link to the
user guide instead of the repo root. The hub-picker itself remains without a
dedicated ? button — this is a HA framework limitation.

## Status

- [x] Timeline file created
- [x] Version bumped to 3.3.1.0
- [x] Manifest documentation URL updated (both files)
- [x] Broken mirror anchor fixed (all 4 strings/translation files)
- [x] options.init title added (all 4 strings/translation files)
- [x] JSON validation passes
