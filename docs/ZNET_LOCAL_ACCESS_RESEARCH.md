# ZNet Local Access Research — What Is Actually Reachable

> **Status:** research only. No code, README or integration changes.
>
> **Question:** how do we make legacy TellStick Net/ZNet hardware future-proof —
> full protocol support without Telldus Live, without new hardware, and without
> relying on Telldus as a company?
>
> **Sources:**
>
> 1. `tellstick-znet-lite-v2-1.3.2.bin` in this repo, extracted and inspected.
> 2. One live TellStick ZNet Lite v2 on a LAN (2026-10-23). Firmware version
>    was not queried; the shipped-version analysis is 1.3.2.
> 3. Public project history and issue trackers (links below).

---

## Verdict

The ZNet has **four** ways in. Three of them are gated by Telldus, and the
gate is not a password we can recover — it is a vendor identity that has to
still exist:

| Interface                    | Path                                   | Auth                                              | Vendor dependency                              | Verdict     |
| ---------------------------- | -------------------------------------- | ------------------------------------------------- | ---------------------------------------------- | ----------- |
| UDP `30303` / `42314`        | `productiontest/Server.pyc`            | **none**                                          | none                                           | ✅ open      |
| Local REST API `/api/*`      | `api/ApiManager.pyc`                   | Bearer token                                      | **Telldus OpenID login** to mint it; ≤ 1 yr TTL | ❌ vendor-gated |
| Local plugin (`.zip` + egg)  | `pluginloader/Loader.pyc`              | GPG keyring `/etc/upgrade/plugins.keyring`        | Telldus Support must enable + approve the key   | ❌ vendor-gated |
| Firmware upgrade             | `Board.doUpgradeImage` → `sysupgrade`  | GPG signature `/etc/upgrade/telldus.gpg`          | Telldus signing key                            | ❌ vendor-gated |

The only interface with **no vendor dependency at all** is the unauthenticated
UDP socket — which is exactly why this integration works while every other
project stalled. Its limit is not permissions but a bug: `handleSend()`.

Replacing the firmware is therefore the only route to full protocol support
that does not depend on Telldus, and it requires physical access once per unit.

---

## Method

### Firmware image

```text
$ file tellstick-znet-lite-v2-1.3.2.bin
firmware 72 v6101 OpenWrt r49388, 16252928 bytes or less,
at 0x200 1247448 bytes, at 0x100000 11110198 bytes
```

| Property      | Value                                             |
| ------------- | ------------------------------------------------- |
| Image format  | Vendor header at `0x0` ("OpenWrt" + `r49388`)     |
| Kernel blob   | `0x200`, 1 247 448 bytes                          |
| Rootfs        | SquashFS 4.0, XZ, 256 KiB blocks, at `0x130ad8`   |
| Extracted     | 3 290 files (`PySquashfsImage`)                   |
| Target        | `ar71xx/generic`, kernel 4.1.23                    |
| Web stack     | Python 2.7 · CherryPy 3.7.0 · Genshi 0.7 · ws4py  |
| TLS           | OpenSSL 1.0.2h (May 2016)                         |
| RF front end  | USB serial `hwgrep://1781:0c32`                   |
| **PHP**       | **none — no `php` binary, no `.php` files**       |

Note for the record: a PHP vulnerability is not applicable to this device. The
web UI is Python. See `ZNET_FIRMWARE_ANALYSIS.md` for the protocol-level ground
truth extracted from the same image.

### Live device

Reachable at `192.168.1.2`, all API calls made over plain HTTP on port 80.

---

## 1. The local API exists — and is vendor-gated

### The documented flow

Telldus documents a device-local token grant, not a password
([authentication.rst](https://github.com/telldus/tellstick-server/blob/master/docs/api/authentication.rst)):

```bash
# 1. request a temporary token
curl -i -X PUT -d 'app=Example app' http://DEVICE_IP/api/token
#    → {"authUrl": "http://DEVICE_IP/api/authorize?token=…", "token": "…"}

# 2. user opens authUrl and approves

# 3. exchange for an access token
curl -i "http://DEVICE_IP/api/token?token=REQUEST_TOKEN"

# 4. call the API
curl -i -H "Authorization: Bearer ACCESS_TOKEN" \
  "http://DEVICE_IP/api/devices/list?supportedMethods=3"

# 5. optional renewal
curl -i -H "Authorization: Bearer ACCESS_TOKEN" http://DEVICE_IP/api/refreshToken
```

The shipped authorize page (`api/templates/authorize.html`) offers grant
lengths of one day, one week, one month or **one year**, plus an
"Auto renew access" checkbox. There is no indefinite token.

### Why it is gated

The authorize page is served by `web/base/Server.pyc`, which authenticates
through registered `IWebRequestAuthenticationHandler` implementations. In the
whole rootfs there is exactly **one** implementation:

```text
$ grep -rl 'IWebRequestAuthenticationHandler' usr/lib/python2.7/site-packages
…/web/base/__init__.pyc          (the interface itself)
…/web/base/Server.pyc            (the framework)
…/tellduslive/web/WebRequestHandler.pyc   ← the only provider
```

That provider contains:

```text
http://login.telldus.com
openid.consumer / openid.store          (python-openid)
/tellduslive/login
/tellduslive/authorize
loginEmail, loginFailed.html, loginSuccess.html
```

So the device's only login path is **Telldus OpenID**. There is no local
admin password, no offline fallback, and `web/base/Server.pyc` even has a
`/web/authFailed?reason=noAuthHandlersConfigured` branch for the case where
none is available.

### Confirmed on hardware

```console
$ curl -i "http://192.168.1.2//api/authorize?token=test"
HTTP/1.1 303 See Other
Date: Fri, 23 Oct 2026 04:54:29 GMT
Content-Length: 102
Content-Type: text/html;charset=utf-8
Location: http://192.168.1.2/web/login
Server: CherryPy/3.7.0
Set-Cookie: session_id=b05f…; expires=…; httponly; Path=/

This resource can be found at <a href="http://192.168.1.2/web/login">…</a>
```

`/api/authorize` redirects to `/web/login` before it renders the form. Since
that login resolves to `login.telldus.com`, **a token can only be minted while
Telldus' identity service is alive**. The hypothesis is therefore closed, not
open: the API is not a future-proof interface.

### The failure mode this creates

| Event                              | Consequence                                                |
| ---------------------------------- | ---------------------------------------------------------- |
| `login.telldus.com` goes away      | No new token can ever be issued on any unit                |
| Token expiry (max 1 year)          | Existing integrations stop with `401`                      |
| Factory reset / flash corruption   | All device tokens gone; unrecoverable without Telldus      |
| Network left offline                | Token still expires on schedule                            |

---

## 2. Why previous projects stalled

This is not a new finding — it is the same wall, hit repeatedly:

| Project                                              | Outcome                                                                                                                             |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| HA `tellduslive` (local mode)                         | 401 after expiry ([#50280](https://github.com/home-assistant/core/issues/50280)), manual yearly renewal ([#118997](https://github.com/home-assistant/core/issues/118997)), authorize 404/403 ([#104968](https://github.com/home-assistant/core/issues/104968), [#132435](https://github.com/home-assistant/core/issues/132435), [#140496](https://github.com/home-assistant/core/issues/140496)) |
| openHAB Tellstick binding                             | Bearer token, but binding does **not** auto-refresh; manual renewal at least yearly                                                  |
| `perbrage/node-red-contrib-telldus-zwave-v2-local`    | Last code commit 2018; maintainer left the platform; polling reportedly locked up the device ([#10](https://github.com/perbrage/node-red-contrib-telldus-zwave-v2-local/issues/10)) |
| `majori/tellstick-adapter` (WebThings)                | Local API supported, last release 2021-01-09, unmaintained                                                                          |
| `mifi/telldus-api`                                    | Requires `telldus-local-auth` browser approval; token kept alive only while requests continue                                       |
| `Pinta365/tellstick-local-server`                     | 2018, subset of API, author notes local API docs are thin                                                                           |
| `quazzie/tellstick-plugin-mqtt-hass`                  | Correct idea, but install requires Telldus Support to enable local plugins and approve the developer key                            |

Vendor status, for completeness: no official shutdown of Telldus Live was
confirmed during this research; the developer portal and firmware changelog are
still up, and the December 2023 outage plus `429` rate limiting is documented
in HA issues. The risk is therefore commercial, not announced — which is
precisely why the design should not depend on it.

---

## 3. What the device can do internally

The RF stack is **complete**; only the network door in front of it is broken.

**Real path** — `rf433/RF433.pyc`:

```text
Protocol.protocolInstance(protocol)
  → setParameters(parameters from the device record)   # code, system, units, …
  → stringForMethod(method, level)                     # real level, not None
  → prefixes(…) → RF433Msg('S', bytes, prefixes)       # R / P preserved
  → queue()
```

**Crippled path** — `productiontest/Server.pyc`:

```python
protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
msg = protocol.stringForMethod(msg['method'], None)
CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

All 18 protocol encoders are registered in `rf433/Protocol.pyc`, which also
exposes `methodsForProtocol()` and `parametersForProtocol()`.
`telldus/DeviceApiManager.pyc` adds API calls named `list`, `info`, `command`,
`dim`, `bell`, `learn`, `up`, `down`, `stop`, `rgb` over fields including
`protocol`, `system`, `name` and `state` — i.e. the capability behind the
vendor gate is full protocol support *and* real dim levels.

The ungated UDP door exposes none of that: unit off-by-one, `house`/`unit`
only, no `R`/`P`, `level` always `None`. That is the entire protocol gap
documented in `ZNET_PROTOCOL_PORTING_GUIDE.md`.

---

## 4. Consequence: what future-proofing requires

Only two no-new-hardware routes reach full protocol support, and **both need a
root shell once per device** (UART/console being the realistic mechanism):

### Option A — patch `handleSend()` (minimal)

Place a patched `productiontest/Server` module in the writable overlay so it
shadows the read-only rootfs copy, restart `telldus-server`. Raw `S` bytes then
reach `rf433` over UDP, so every encoder already in this repo works on ZNet —
no token, no API, no vendor. Survives independently of Telldus forever, and is
reversible from an overlay backup.

Cost: one UART session per unit. Benefit: full TX protocols, correct `R`/`P`,
`level` handling, on **stock firmware**, keeping Z-Wave intact.

### Option B — community image (total)

Same ar71xx image format, running `telldusd` against the internal USB dongle
(`1781:0c32`, Telldus USB class) — the existing **Duo backend** then works
unchanged. Zero vendor code anywhere.

Cost: a maintained MIPS fork, UART flashing per unit, **loss of Z-Wave and
RGB/Learn**, and no vendor recovery if a flash fails. Only worth it if Z-Wave
is irrelevant to the user.

### Rejected

- **Plugin route** — requires Telldus to enable local plugins and approve a
  developer key per device, and they frequently do not answer.
- **API route** — confirmed vendor-gated (§1); tokens expire and cannot be
  reissued after the identity service disappears.
- **New hardware** (Duo, ESP, rtl_433 TX) — excluded by the goal: the point is
  to keep existing hardware working.

---

## 5. Open questions (need hardware)

1. **Overlay shadowing.** Python 2 prefers a `.pyc` newer than its `.py`. A
   patched `.py` in `/overlay/upper/…` must either carry a newer mtime or be
   accompanied by a matching `.pyc`. Verify before promising the patch.
2. **Overlay space and persistence.** Free space in `rootfs_data`, survival
   across `sysupgrade` (see `/etc/sysupgrade.conf` — nothing preserved by
   default), and whether `procd` respawns cleanly after a bad patch.
3. **UART / recovery.** Whether the board exposes console pads and whether
   U-Boot offers TFTP recovery. This decides whether Option A is safe to
   recommend and whether Option B can be un-bricked.
4. **Z-Wave after Telldus.** On stock firmware, Z-Wave control by HA needs an
   API token, so it dies with the identity service; on a custom image there is
   no Z-Wave driver. Needs its own investigation before any migration advice.
5. **Firmware 1.3.3 beta** — not analysed; assume identical for now.
6. **Token behaviour on a reset unit** — moot while `/web/login` is OpenID, but
   worth re-testing if Telldus ever returns.

---

## References

Firmware evidence (this repo):

- `docs/ZNET_FIRMWARE_ANALYSIS.md` — UDP protocol ground truth
- `docs/ZNET_PROTOCOL_PORTING_GUIDE.md` — per-protocol TX status
- `docs/telldus-live-shutdown-migration-plan.md` — earlier migration sketch

External:

- <https://github.com/telldus/tellstick-server/blob/master/docs/api/authentication.rst>
- <https://tellstick-server.readthedocs.io/en/v1.0.12/api.html>
- <https://developer.telldus.com/wiki/FirmwareVersion>
- <https://www.home-assistant.io/integrations/tellduslive/>
- <https://github.com/openhab/openhab-addons/tree/main/bundles/org.openhab.binding.tellstick>
- <https://github.com/home-assistant/core/issues/50280>
- <https://github.com/home-assistant/core/issues/118997>
- <https://github.com/home-assistant/core/issues/104968>
- <https://github.com/home-assistant/core/issues/132435>
- <https://github.com/perbrage/node-red-contrib-telldus-zwave-v2-local>
- <https://github.com/quazzie/tellstick-plugin-mqtt-hass>
- <https://github.com/mifi/telldus-api>
