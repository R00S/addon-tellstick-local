# TellStick Local — What's new

Home Assistant shows this file under **Settings → Apps → TellStick Local →
Changelog**, and on the update card. It is read straight from here, so keep it
user-facing: what changed, and what to do after updating. Technical detail
belongs in `docs/`.

Newest first. The newest `## ` heading matches the version in
`custom_components/tellstick_local/manifest.json` (CI checks it).

## 3.4.1.1

### Fixed

- Choosing **Add it anyway** for a code another device already uses now adds a
  second device on that code instead of replacing the existing one. Reported
  with Anslut/comen devices.
- Renaming a device that shares its code with another device no longer moves it
  back onto the other device's entry.

### After updating

- Existing devices keep working; nothing has to be reconfigured.
- If an earlier attempt replaced a device, add that device once more.

Coming from 3.3.3.0 (last stable)? This update also contains everything in the
3.4.0.x sections below: TellStick Net v1 support, Luxorparts, and devices that
stay deleted once removed.

## 3.4.1.0

### New

- Adding a device now uses sliders for the house code and the unit, starting at
  the next code no other device uses instead of an empty text field.
- If the code you pick is already used by another device, a warning names that
  device first, with **Change** and **Add it anyway** to choose from.

## 3.4.0.15

### Fixed

- Deleting a device now really deletes it, including a card that holds several
  switches at once. Deleted devices no longer come back on the next radio event
  or after a restart.

## 3.4.0.0 – 3.4.0.14

### New

- TellStick Net v1 (and ZNet): dimming works, and every protocol the Duo can
  send now goes out as raw pulse frames instead of being dropped by the
  firmware. Issue #130.
- Mirror units get the same raw pulse support.
- Luxorparts: a generated pool of 304 distinct code pairs. The beta device type
  offers the 24 pairs proven on hardware behind one slider, the experimental
  type the remaining 280.

### Fixed

- Deleting a device no longer lets auto-add or a restart bring it back.
