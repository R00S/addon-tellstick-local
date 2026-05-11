# Branch: fix-question-marks-in-readme — 3.3.0.x

## Problem

- Some "?" question mark help buttons in config flow steps link to the repo README root (`https://github.com/R00S/addon-tellstick-local`) instead of the User Guide.
- Some flow steps have no "?" at all.
- None of the "?" buttons link to specific anchors in `docs/USER_GUIDE.md`.

## Root Cause

No `description_url` field was set on any config flow step in `strings.json` / `translations/en.json`. HA uses the manifest's `documentation` URL as fallback — which is the repo root/README.

## Fix

Add `description_url` to every config flow step (config, options, config_subentries) in all four strings/translations files, pointing to the matching section anchor in `docs/USER_GUIDE.md`.

Files to update:
- `custom_components/tellstick_local/strings.json`
- `custom_components/tellstick_local/translations/en.json`
- `tellsticklive/rootfs/usr/share/tellstick_local/strings.json`
- `tellsticklive/rootfs/usr/share/tellstick_local/translations/en.json`

Synchronise the runtime files with custom_components at the same time (they were behind on the inline `[📖 User Guide: ...]` links added in an earlier session).

## Status

- [x] Timeline file created
- [ ] `description_url` added to all steps
- [ ] Runtime files synced and updated
- [ ] Manifest version bumped
