# TellStick Net v1 — local TX silently dropped (issue #114)

> **Issue:** https://github.com/R00S/addon-tellstick-local/issues/114
> **Symptom:** On the *original* TellStick Net (v1, C firmware), devices add fine
> and `send` UDP packets demonstrably leave Home Assistant, but the device never
> transmits (no LED blink, receiver silent). Telldus Live controls the same
> receiver fine. Two independent reporters (fw 4 and fw 17).

## TL;DR

**The packets we send are provably correct.** They are byte-identical in
structure to Telldus' own reference client for the original TellStick Net
(`client/send.py` in telldus/tellstick-net), and a byte-exact simulation of the
published v1 firmware parser reaches TX with the right house/unit/method.

So the bug is **not** in our encoding. The most likely explanation for the
non-reproduction is that all TX verification done in this project so far
happened on the **Python-firmware units (Net v2 / ZNet)** — the original Net v1
runs a closed production build whose local `send` handler we cannot inspect,
and the open-source firmware tree (which *does* implement `send`) is a
development build that Telldus' own tooling refuses on production hardware.

**Decisive next step:** run `tools/probe_net_send.py` against a reporter's
unit (5 packet variants, watch the LED) — results map 1:1 to the fix.

## What was verified (sources)

### 1. Wire format — matches Telldus' own reference byte for byte

Telldus' test client for local control
([`telldus/tellstick-net/client/send.py`](https://github.com/telldus/tellstick-net/blob/master/client/send.py))
builds:

```python
msg = "4:sendh8:protocol%X:%s5:model%X:%s5:housei%Xs4:uniti%Xs6:methodi%Xss" \
      % (len(protocol), protocol, len(model), model, house, unit, method)
```

Our integration sends (issue #114 values, house=292130 unit=1 ON):

```
4:sendh8:protocol7:arctech5:modelC:selflearning5:housei47522s4:uniti0s6:methodi1ss
```

Identical structure: `send` name, `h`-dict with keys `protocol`, `model`,
`house`, `unit`, `method`, ints as `i<hex>s`, `unit` 0-indexed.

The official protocol doc
([archived TellStickNet.html](https://web.archive.org/web/20200812100636/http://developer.telldus.com/doxygen/html/TellStickNet.html))
confirms the message format and documents `send` with `S`/`P`/`R` **as dict
keys**.

### 2. Firmware parser — simulation of our exact bytes reaches TX

A byte-exact Python port of the published firmware parser
(`firmware/livemessage.c`, `tellsticknet.c::send()`,
`transmit_arctech.c::sendArctechSelflearning()`) was run against our actual
`encode_packet()` output:

```
name='send' -> TX: house=292130 unit(button)=0 method=1 (ON) repeats=10 pause=11ms
```

Same result for molobrakos' "works like a charm" packet
(`4:sendh8:protocol7:arctech5:modelC:selflearning5:housei11cb0dbs4:uniti0s6:methodi2ss`,
molobrakos/tellsticknet#23). Parser trace notes:

- `hexToByte()` accepts upper **and** lower case hex (`common.c`), so our
  uppercase `%X` lengths (`C:selflearning`) and uppercase int hex parse fine.
- `LMFindHashString()` restarts from the hash start on every call → key order
  is irrelevant.
- v1 `send()` only forwards `protocol=arctech` + `model=selflearning` to the
  native transmitter; anything else without an `S` key is silently dropped.

### 3. RF frame — matches telldus-core bit for bit

`transmit_arctech.c::sendArctechCommand()` vs telldus-core
`ProtocolNexa::getStringSelflearningForCode()` (extracted from
`telldus-core_2.1.3-beta1.orig.tar.gz` in this repo):

| Field    | telldus-core              | v1 firmware              | ours        |
| -------- | ------------------------- | ------------------------ | ----------- |
| house    | 26 bits, `1..67108863`    | 26 bits (`sendBits` ×4)  | int ✓       |
| group    | `01` (zero)               | `sendZero()`             | implicit ✓  |
| on/off   | ON=`10`, OFF=`01`         | `method==1`→one else zero | 1=ON, 2=OFF ✓ |
| unit     | `getIntParameter(1,16)-1` | raw value as 4-bit field | `unit-1` ✓  |

LEARN in telldus-core = a plain ON frame. The v1 native dict has no learn:
`method=32` falls to `sendZero()` → an **OFF frame**. Pairing a receiver via
the v1 native path therefore sends the wrong frame (minor, pre-existing).

## Why it cannot be reproduced

The `net` backend's TX path was developed and verified against the **ZNet/Net v2
Python firmware** (decompiled `handleSend()` — see
`docs/ZNET_FIRMWARE_ANALYSIS.md`). The original Net v1 is a different animal:

1. **The open-source firmware is a development build.** `firmware/common.h`
   hardcodes `FIRMWARE_VERSION "X"`, and Telldus' own `client/send.py` *refuses
   any device whose firmware is not `X`* ("Not using correct firmware").
   Production units report numeric versions (4, 17). Local `send` was
   implemented in the open tree in 2013 (`Implement protocol Arctech
   Selflearning`); whether/ how the closed production builds (4 → 17) include
   it is unverifiable from here — and **no third party has ever confirmed the
   native dict path on a production original Net**. molobrakos' confirmed
   working sends on v1 hardware were raw `S` bytes (dim), and the
   "works like a charm" native dict in molobrakos#23 was against a **ZNet v2**
   (its log shows S-only packets failing — Python `handleSend()` behaviour).

2. **The v1 and the v2/ZNet look identical from the outside** (same case, same
   UDP ports). If the test unit's discovery reply starts with
   `TellstickNetV2:` or `TellstickZnet:` it is *not* the hardware the
   reporters have — theirs reply `TellStickNet:<mac>:<code>:<firmware>`.

3. **Repeat-parameter (`P`/`R`) placement differs between sources** —
   three mutually inconsistent variants are on record:
   - official doc: `P`/`R` **inside** the dict (`{'S':…,'P':20,'R':15}`);
   - open-source firmware: reads `P`/`R` from inside the dict
     (`LMFindHashString("P")`);
   - molobrakos PR #27 (2020): appends `1:P…1:R…` **after** the dict and
     reports "huge improvement in stability… feels snappier" — which implies
     the production firmware it ran against *did* read them from there
     (otherwise repeats would stay at the 10×11 ms defaults and nothing
     would feel snappier).

   Our packet carries no `P`/`R` at all. That should fall back to defaults and
   still TX — but given the above, the production `send()` parser is clearly
   not identical to the published tree, and its exact contract is unknown.

## Ranked hypotheses

1. **Production v1 firmware does not implement `send` (or its native arctech
   path) at all.** Fits: complete silence (no LED), no errors anywhere, Live
   works (different path), events/discovery still work, Telldus' own send
   client limited to 'X' builds.
2. **Production `send()` parses `P`/`R` differently and strict-parses the
   packet** (e.g. requires the molobrakos trailing pairs). Fits the PR #27
   testimony; contradicted only by the open tree.
3. **Datagrams never reach the device** (VM/bridge/checksum offload —
   reporter 2 runs HA in a VM on a Synology NAS). Fits "no LED" but would
   also break `reglistener`/events. Discriminator below.

## The discriminating test — `tools/probe_net_send.py`

Run from any machine on the device's LAN:

```
python3 tools/probe_net_send.py 192.168.1.244 --house 292130 --unit 1
```

It sends five variants (A: our current packet; B: `P`/`R` in dict;
C: trailing `P`/`R`; D: raw S pulse train; E: S + `P`/`R`), asks after each
whether the LED blinked / the receiver responded, then listens 30 s for RF
events (press a remote). Outcome → fix:

| Result                          | Conclusion                                        | Fix                                                            |
| ------------------------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| All five blink                  | TX path fine; codes/network issue                 | look at house/unit config instead                              |
| A silent, B or C blink          | `P`/`R` placement mismatch                        | add `P`/`R` (dict or trailing), gated on product `TellStickNet` |
| Only D/E blink                  | native arctech dict unsupported in this firmware  | encode arctech on/off/learn as raw `S` bytes for v1            |
| None blink                      | local `send` not implemented in production fw     | document v1 TX as unsupported; keep events                     |
| 0 events in listen phase        | UDP delivery broken (VM/firewall)                 | fix network, re-test                                           |

Note D uses the firmware's `rfSend()` playback path, which the published source
shows works for **any** protocol on v1 — and molobrakos confirmed S-bytes TX
(dim) on a production original Net. If D works, the permanent fix is small:
the repo already has the arctech pulse encoder (`_arctech_dim_pulse_train`
pattern in `net_client.py`), and the discovery reply's product name
(`TellStickNet` vs `TellstickNetV2`/`TellstickZnet`) can be threaded from
config flow into `TellStickNetController` to select the v1 encoding.

## Also worth asking the reporters

1. Do RF **events** from that Net (remote button presses, sensors) ever reach
   HA? (Yes → UDP delivery works and the `send` verb is the problem; No →
   hypothesis 3.)
2. Exact discovery reply string (`TellStickNet:…` vs `TellstickNetV2:…`) —
   confirms the hardware generation unambiguously.
3. For reporter 1: the debug report line "Discovered UIDs this session: 1" is
   counted at manual add too — it does not prove events were received.
