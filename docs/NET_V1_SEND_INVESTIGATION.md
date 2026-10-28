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

---

# Round 2 — probe results and the listener-socket shadow (2026-10-27)

## New field data (tomwickstromse, firmware 17, Nexa selflearning-dimmer)

- Probe run from a Mac on the same LAN: **all five variants (A–E) work** —
  LED blinks and the receiver responds, including A, byte-identical to what
  the integration sends. Packet encoding is therefore exonerated on real
  production hardware.
- Immediately afterwards the same light commanded through HA / TellStick Local
  3.3.1.5: no LED blink, no response. Telldus Live keeps working.
- Reporter's conclusion: "Could the issue be related to how the integration
  opens or binds its UDP socket?" — that is now the leading hypothesis.

Remaining difference between the probe and the integration: not the bytes,
but **the connection state** (the integration sends `reglistener` first and
keeps the socket registered; the probe never registers) and **the source
socket** (both use port 42314 when the integration's bind succeeds).

## The v1 firmware's two sockets on one port (from published source)

`localaccess.c` opens the command socket:

```c
localSocket = UDPOpen(LOCAL_ACCESS_PORT, NULL, LOCAL_ACCESS_PORT);  // 42314
```

`tellsticknet.c` implements the listener registration and event push:

```c
void registerListener() {
    memcpy(&remote, &UDPSocketInfo[localSocket].remote, sizeof(remote));
    localPort = UDPSocketInfo[localSocket].remotePort;   // registrant's SOURCE port
    listenerActive = 1;
    if(s != INVALID_UDP_SOCKET) { UDPClose(s); s = INVALID_UDP_SOCKET; return; }
}

void sendToLocalListeners() {
    if (!listenerActive) return;
    if(s == INVALID_UDP_SOCKET)
        s = UDPOpen(localPort, &remote, localPort);      // ← opened on first event
    ...UDPPut/UDPFlush...
}
```

So on the **first RF event after registration**, the firmware opens a second
socket `s` bound to *the registrant's source port* and pointed at the
registrant's address. **If the client registers from source port 42314 — as
our integration does — `s` collides with the firmware's own command socket,
which also lives on 42314.** Telldus' own reference client registers from an
ephemeral port and never triggers this.

Why the collision eats commands (Microchip TCPIP Stack `UDP.c`):

- `UDPProcess()` delivers each datagram to exactly **one** socket
  (`SocketWithRxData = FindMatchingSocket(...)`).
- `FindMatchingSocket()` returns the *first* socket whose
  (localPort, remotePort, remoteIP) all match the packet's
  (destPort, sourcePort, sourceIP); failing that, the *last* socket with a
  matching localPort (and rebinds it to the sender).
- `s` was created with remote = (registrant IP, 42314), so **the registered
  client's own commands are the only traffic that exact-matches `s`**.
- `localAccessTask()` reads only `localSocket`:
  `if (!UDPIsGetReady(localSocket)) return;` and `UDPIsGetReady()` returns 0
  whenever `SocketWithRxData != s_requested`. A command delivered to `s` is
  never read and is silently discarded with the next packet.

Which of `localSocket`/`s` wins depends on their socket-array slots
(`UDPOpen` takes the first free slot; DHCP/DNS churn moves slots around), so
the drop may be boot-dependent — consistent with "always fails" once an event
has been pushed on the affected units.

This also explains why the Mac probe works: it never sends `reglistener`, so
`sendToLocalListeners()` never opens `s`, so nothing can shadow the command
socket. And the last probe run can make things *worse* for HA: the probe's
packets partially match `localSocket` and rebind its remote to the Mac's
address, after which only `s` exact-matches HA's traffic.

## Second candidate: transport (not yet excluded)

`UDPProcess()` **verifies the UDP checksum whenever the field is non-zero and
silently `MACDiscardRx()`es on mismatch** — the classic fate of packets with
broken checksum offload leaving a VM. Reporter 2 runs HAOS in a VM on a
Synology NAS.

Note also that nothing in this thread confirms the device ever *received*
anything from HA: "Connection: OK" is our own fire-and-forget `reglistener`
(there is no reply), device-adding is catalog-based, and "Discovered UIDs"
is counted at manual add. Only tcpdump (egress) was inspected.

## Discriminators (probe phase 2 + two data points)

`tools/probe_net_send.py` phase 2 reproduces the integration's state step by
step from a known-good machine:

| Test | State reproduced                                                |
| ---- | --------------------------------------------------------------- |
| F    | `reglistener` then `send`, same socket (42314)                    |
| G    | `reglistener` + RF event + `send`, same socket = the integration  |
| H    | same, but `send` from a separate ephemeral socket                |
| I    | `reglistener` + `send`, both ephemeral (Telldus reference style) |

| Result                       | Conclusion                                        | Fix                                              |
| ---------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| A works, G fails, I works    | listener-socket shadow confirmed                  | register + send from an ephemeral port in the integration |
| A works, G works             | state not the cause; transport or host-specific   | run probe on the HA host; check tcpdump headers  |
| All fail from the HA host    | packets die in the network path (VM bridge / NAT) | network fix, no code change                      |
| tcpdump shows `bad udp cksum`| checksum offload drop in device stack             | disable offload on the VM NIC / force checksum   |

Data still wanted from the reporters:

1. Run the probe **on the HA host itself** (Synology SSH or the HAOS SSH
   add-on) and compare with the Mac run.
2. From the existing tcpdump capture: the outgoing packet's **source port**
   and any tcpdump checksum annotation (`bad udp cksum` / `incorrect`).
3. HA log lines at connect: `Net: bound to port 42314 for …` vs
   `Port 42314 already bound; using ephemeral port …`.

## Candidate fix (pending phase-2 confirmation)

Register and send from an **ephemeral source port** instead of binding 42314.
This is compatible with both generations: the v1 firmware pushes events to
the registrant's source address (`sendToLocalListeners` → `s`), and the ZNet
v2 Python firmware pushes `RawData` to `self.clientAddress` (the `reglistener`
source) — neither requires the client to bind 42314. The current 42314 bind
exists only to catch hypothetical broadcasts, and on v1 it is precisely what
causes the collision.
