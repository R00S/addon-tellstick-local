# Branch timeline: adapt-chores-and-create-guide — 3.2.0.x

## Goal

Import repo-management practices from `R00S/meater-in-local-haos`:

1. Copy and adapt `CHORES.md` for this repository.
2. Create `docs/USER_GUIDE.md` — a standalone, comprehensive user guide.
3. Add contextual user-guide links in `strings.json` / `translations/en.json`
   config-flow descriptions (equivalent to `_openHelp()` calls in meater's
   `panel-class-template.js`).
4. Update `README.md` with a prominent `## 📖 User Guide` section.
5. Version bump to **3.3.0.0** as requested.

## Session log

### 2026-05-11 — Initial implementation

- Created this timeline file.
- Created `CHORES.md` (adapted from meater-in-local-haos — references
  `strings.json` description fields instead of `panel-class-template.js`
  `_openHelp()` calls, since this project uses HA config flows not a custom
  JS panel).
- Created `docs/USER_GUIDE.md` — full user guide covering installation,
  pairing (auto-add + teach), editing, grouping, mirror/extender, removal,
  supported devices, events, debugging, troubleshooting, known limitations,
  and migration from the old add-on.
- Updated `README.md` — added `## 📖 User Guide` section near the top with
  link to `docs/USER_GUIDE.md`.
- Updated `strings.json` and `translations/en.json` — appended a
  `[📖 User Guide]` markdown link to the descriptions of five key
  config-flow steps (hassio_confirm, add_rf_device, settings, confirm/teach,
  group_device).
- Bumped version to `3.3.0.0` in both `manifest.json` files.
