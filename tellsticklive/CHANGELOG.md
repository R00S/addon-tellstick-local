# TellStick Local — What's new

Home Assistant shows this file under **Settings → Apps → TellStick Local →
Changelog**, and on the update card. It is read straight from here, so keep it
user-facing: what changed, and what to do after updating. Technical detail
belongs in `docs/`.

Newest first. The newest `## ` heading matches the version in
`custom_components/tellstick_local/manifest.json` (CI checks it).

## 3.4.2.1

### Fixed

- The transmitter entity added in 3.4.2.0 never appeared. Home Assistant
  registered it as disabled — a preference stored on the integration entry —
  so it was hidden and could not be chosen as a sender. It is now registered
  enabled, whatever that preference says. If you already installed 3.4.2.0,
  update and restart: the entity switches itself back on.

### After updating

- Requires Home Assistant 2026.5 or later.
- Nothing to reconfigure; your own devices, codes and automations are
  untouched.

## 3.4.2.0

### New

- The TellStick can now be used as a radio frequency transmitter by other
  integrations. Until now it only controlled its own 433 MHz devices; it can
  now send whatever another integration asks it to send — for example a Novy
  cooker hood or a set of Honeywell string lights added through Home
  Assistant's own device integrations. Pick the TellStick as the transmitter
  when that integration asks, and its commands go out through your TellStick.
  Works on a TellStick Duo and on the original TellStick Net (v1).
- Long pulses and gaps are split into several shorter ones, so signals with a
  long start or end pulse can be sent too. A mirror reinforces these commands
  exactly like your own devices' commands.

### After updating

- Requires Home Assistant 2026.5 or later.
- Nothing to reconfigure: devices, codes and automations are untouched. No
  new device or entity appears unless another integration asks for a
  transmitter.

## 3.4.1.5

### Changed behaviour

- None — this is housekeeping on top of 3.4.1.4, with nothing new to see or
  do. After removing the huge house-code list from the add-device dialog, the
  same review was run over the rest of the integration, starting with the
  unit slider in that dialog. No other place builds a list of every possible
  code, and the unit slider now walks its range instead of copying it, so a
  wide widget can never freeze Core this way again.

### After updating

- Nothing to reconfigure. Devices, codes and automations are untouched.

## 3.4.1.4

### Fixed

- Pressing **Confirm** in the add-device dialog no longer freezes or restarts
  Home Assistant Core. Building the house/unit sliders for self-learning
  devices (Nexa, Proove, Anslut and similar) prepared a list of every possible
  house code — over 67 million numbers — needing gigabytes of memory and a
  multi-second stall. The first free code is now found without that list.
- This was the real cause of the Core restarts reported while pairing on a
  TellStick Net v2 / ZNet (issue #131).

### After updating

- Adding a device works as before: pick a brand, confirm, and the sliders
  start on the first code no stored device uses.
- Devices already added need no change.

## 3.4.1.3

### Fixed

- The **"set up as a mirror"** picker no longer lists your 433 MHz devices as
  if they were TellSticks. Only real hubs (a Duo, or a Net/ZNet) are offered;
  discovered or ignored device entries are left out.
- **Move device to another hub** uses the same filter and no longer offers
  those entries either.

### After updating

- Nothing to reconfigure. If you picked a device by mistake while setting up
  a mirror, delete that mirror entry and add it again.

## 3.4.1.2

### Fixed

- Pairing a self-learning switch (Nexa, Proove, Anslut and similar) through a
  TellStick Net v2 / ZNet now sends the normal ON code instead of a dedicated
  learn frame. Receivers store the ON code, which is what their own remotes
  send, so pairing completes.
- This also stops the learn step from asking the Net v2 / ZNet firmware for a
  frame it cannot build properly, which is the suspected cause of Home
  Assistant Core restarting while pairing (issue #131).
- TellStick Net v1 is unchanged: it still sends its raw learn pulse train,
  which is confirmed on hardware.

### After updating

- Put the receiver in learn mode, then press **Send learn signal** (or add the
  device again) to pair it.
- Devices that already work need no change.

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
