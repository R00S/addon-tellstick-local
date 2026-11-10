# Net/ZNet Firmware Analysis — Ground Truth

> **Source:** Decompiled from `tellstick-znet-lite-v2-1.3.2.bin` (in repo root).
> The firmware is an OpenWrt image with a SquashFS rootfs containing Python 2.7
> `.pyc` files.  Extracted with `PySquashfsImage`, decompiled with `uncompyle6`.

This document serves as the **ground truth** for how the TellStick Net v2 / ZNet
firmware handles local UDP commands.  All protocol behavior described here was
verified against the actual firmware binary — not documentation or third-party
implementations.

## Hardware Variants

From `Board.pyc :: Board.cfgs`:

| Product                | Board Config Key         | 433 MHz Interface         |
| ---------------------- | ------------------------ | ------------------------- |
| TellStick Net v2       | `tellstick-net-v2`       | `hwgrep://1781:0c32` (USB) |
| TellStick ZNet Lite    | `tellstick-znet-lite`    | `/dev/ttyUSB0` (serial)   |
| TellStick ZNet Lite v2 | `tellstick-znet-lite-v2` | `hwgrep://1781:0c32` (USB) |

All three share the same Python firmware codebase (`tellstick-server`).

## Network Architecture

From `productiontest/Server.py`:

```python
class Server(Plugin):
    def __init__(self):
        self.autoDiscovery = SocketServer.UDPServer(('0.0.0.0', 30303), AutoDiscoveryHandler)
        self.commandSocket = SocketServer.UDPServer(('0.0.0.0', 42314), CommandHandler)
```

- **Port 30303** — Auto-discovery: responds to `"D"` broadcast with product info
- **Port 42314** — Command socket: handles `reglistener` and `send` commands

## Auto-Discovery Response

From `AutoDiscoveryHandler.handle()`:

```python
msg = '%s:%s:%s:%s:%s' % (
    product,          # e.g. "TellstickNetV2", "TellstickZnet"
    getMacAddr(...),  # e.g. "ACCA5401E27A"
    Board.secret(),   # activation code
    Board.firmwareVersion(),  # e.g. "1.1.0"
    live.uuid         # TelldusLive UUID
)
```

## Command Handling — The Critical `handleSend()`

From `CommandHandler.handle()` and `CommandHandler.handleSend()`:

```python
class CommandHandler(SocketServer.BaseRequestHandler):
    rf433 = None
    context = None

    def handle(self):
        data = self.request[0].strip()
        self.socket = self.request[1]
        if data == 'B:reglistener':
            server = Server(CommandHandler.context)
            server.reglistener(self.socket, self.client_address)
        msg = LiveMessage.fromByteArray(data)
        if msg.name() == 'send':
            self.handleSend(msg.argument(0).toNative())

    @staticmethod
    def handleSend(msg):
        protocol = Protocol.protocolInstance(msg['protocol'])
        if not protocol:
            logging.warning('Unknown protocol %s', msg['protocol'])
            return
        protocol.setModel(msg['model'])
        protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
        msg = protocol.stringForMethod(msg['method'], None)
        if msg is None:
            logging.error('Could not encode rf-data')
            return
        CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

### Bugs Found

#### Bug 1: Unit+1 Offset

```python
protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
#                                                       ^^^^^^^^^^^^^
```

The handler adds 1 to the unit value before passing it to `setParameters()`.
Protocol encoders then call `intParameter('unit', min, max)` which may subtract 1
internally (e.g. everflourish: `intParameter('unit', 1, 4) - 1`).

**Impact:** Commands target the wrong unit.  If we send `unit=1`:
- Firmware receives 1, adds 1 → `setParameters(unit=2)`
- `intParameter('unit', 1, 4)` returns 2, then `- 1` = **unit_code 1**
- But the device expects **unit_code 0** (for unit 1)

**Compensation:** In `_encode_generic_command()`, we subtract 1 from unit before
sending, so the firmware's +1 results in the correct value.

#### Bug 2: Limited Parameter Passthrough

```python
protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
#                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# Only house and unit — nothing else!
```

Protocols that need additional parameters fail silently:
- **sartano** needs `code` (10-digit string)
- **fuhaote** needs `code` (10-digit string)
- **ikea** needs `system`, `units`, `fade`
- **brateck** needs `house` (8-character DIP string — works, but model is critical)

#### Bug 3: No R/P Prefix Passthrough

```python
CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
#                                                      ^^
# Always empty dict — R and P values are lost!
```

Protocols needing custom repeat/pause values:
- **hasta v1**: `R=10, P=25`
- **hasta v2**: `R=10, P=0`
- **risingsun selflearning**: `P=5`
- **risingsun learn**: `P=5, R=50`

Without these, the signal may be too weak or too fast for the receiver.

## Protocol Stack

From `Protocol.py :: Protocol.protocolInstance()`:

```python
@staticmethod
def protocolInstance(protocol):
    if protocol == 'arctech':     return ProtocolArctech()
    if protocol == 'brateck':     return ProtocolBrateck()
    if protocol == 'comen':       return ProtocolComen()
    if protocol == 'everflourish': return ProtocolEverflourish()
    if protocol == 'fuhaote':     return ProtocolFuhaote()
    if protocol == 'fineoffset':  return ProtocolFineoffset()
    if protocol == 'hasta':       return ProtocolHasta()
    if protocol == 'ikea':        return ProtocolIkea()
    if protocol == 'kangtai':     return ProtocolKangtai()
    if protocol == 'mandolyn':    return ProtocolMandolyn()
    if protocol == 'oregon':      return ProtocolOregon()
    if protocol == 'risingsun':   return ProtocolRisingSun()
    if protocol == 'sartano':     return ProtocolSartano()
    if protocol == 'silvanchip':  return ProtocolSilvanChip()
    if protocol == 'upm':         return ProtocolUpm()
    if protocol == 'waveman':     return ProtocolWaveman()
    if protocol == 'x10':         return ProtocolX10()
    if protocol == 'yidong':      return ProtocolYidong()
    return None
```

**All 18 protocols** are registered.  The protocol stack itself works correctly —
the bugs are in `handleSend()` which sits between our UDP command and the protocol
encoder.

## Event Push — `reglistener` and `RawData`

From `Server.reglistener()` and `Server.rf433RawData()`:

```python
def reglistener(self, sock, clientAddress):
    self.listener = sock
    self.clientAddress = clientAddress

@slot('rf433RawData')
def rf433RawData(self, data, *args, **kwargs):
    if 'data' in data:
        data['data'] = int(data['data'], 16)
    msg = LiveMessage('RawData')
    msg.append(data)
    self.listener.sendto(msg.toByteArray(), self.clientAddress)
```

Key observation: The event data's `data` field is converted from hex string to
integer (`int(data['data'], 16)`) before sending.  Our decoder must handle this
integer format.

## Firewall Rules

From `firewall.telldus`:

```
iptables -A input_wan_rule -p udp --dport 30303 -j ACCEPT    # discovery
iptables -A input_wan_rule -p udp --dport 42314 -j ACCEPT    # commands/events
iptables -A input_wan_rule -p udp -m udp --sport 1900 -j ACCEPT   # UPnP
```

## TX path — verified decompile (2026-11-10)

A fresh extraction and decompile of the same image (SquashFS superblock at
`0x130ad8`, `PySquashfsImage` 0.9.0, `uncompyle6` 3.9.3) settles the questions the
earlier version of this file left open. Reproduce with
`python3 tools/decompile_znet_firmware.py`. The code below is quoted from
`productiontest/Server.py` and supersedes the speculation that used to end this
document.

### `CommandHandler.handle()` / `handleSend()`

```python
def handle(self):
    data = self.request[0].strip()
    self.socket = self.request[1]
    if data == 'B:reglistener':
        server = Server(CommandHandler.context)
        server.reglistener(self.socket, self.client_address)
    msg = LiveMessage.fromByteArray(data)
    if msg.name() == 'send':
        self.handleSend(msg.argument(0).toNative())
    return

@staticmethod
def handleSend(msg):
    protocol = Protocol.protocolInstance(msg['protocol'])
    if not protocol:
        logging.warning('Unknown protocol %s', msg['protocol'])
        return
    protocol.setModel(msg['model'])
    protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
    msg = protocol.stringForMethod(msg['method'], None)
    if msg is None:
        logging.error('Could not encode rf-data')
        return
    CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

What this proves, line by line:

1. **`S`-only packets cannot work.** `msg['protocol']` is a plain dict lookup, so
   a dict without a `protocol` key raises `KeyError` *inside* `handleSend()`
   before any RF code runs. Earlier text here claimed `protocolInstance()` returns
   `None`; that is wrong — the exception happens one line earlier, and there is no
   `try`/`except` around it.
2. **`S` next to `protocol` is ignored.** The `S` that reaches the radio is
   `msg['S']` *after* `msg = protocol.stringForMethod(...)`, i.e. the firmware's
   own encoder output. Our bytes are replaced, not used.
3. **`P`/`R` cannot be set over UDP.** `RF433Msg` supports a `prefixes` dict and
   `commandString()` expands it to `R<n>S…+` for the serial line, but
   `handleSend()` hardcodes `{}`.
4. **No dim level.** `stringForMethod(method, None)`, and `ProtocolArctech`
   computes `newLevel = level / 16`, so a `DIM` method raises `TypeError`
   (`None / 16`). The only dim-ish path is the encoder's own
   `TURNON` + `selflearning-dimmer` → `DIM(255)` redirect.
5. **`unit + 1` is applied by the firmware**, confirming the compensation in
   `_encode_generic_command()`.
6. **`send` is the only TX verb** on the unauthenticated socket: `handle()` acts
   on `send` and `B:reglistener` only.

### The path that does support raw bytes and prefixes

`rf433/RF433.pyc :: DeviceNode._command()` does what `handleSend()` should have
done:

```python
protocol.setParameters(self._protocolParams)
msg = protocol.stringForMethod(action, value)      # real value -> real dim level
...
prefixes = {}
if 'P' in msg: prefixes['P'] = msg['P']
if 'R' in msg: prefixes['R'] = msg['R']
if 'S' in msg:
    self.controller.queue(RF433Msg('S', msg['S'], prefixes, ...))
```

This is the device-manager path behind the local REST API
(`/api/device/command|dim`), which is vendor-gated — see
[`docs/ZNET_LOCAL_ACCESS_RESEARCH.md`](ZNET_LOCAL_ACCESS_RESEARCH.md). The firmware
*can* send arbitrary encoded frames with repeats and real levels; it just never
exposes that to the unauthenticated UDP socket.

### Consequences

- Raw `S` TX on v2/ZNet over UDP is **impossible**, not merely unproven: no packet
  shape reaches `queue()` with our bytes. The v1's `S` playback branch has no ZNet
  counterpart.
- The only routes to raw TX on v2/ZNet remain a patched `handleSend()` in the
  writable overlay (root shell per unit) or a Duo. See
  [`docs/NET_V1_RAW_TX_PLAN.md`](NET_V1_RAW_TX_PLAN.md) for what raw TX unlocks and
  [`docs/ZNET_LOCAL_ACCESS_RESEARCH.md`](ZNET_LOCAL_ACCESS_RESEARCH.md) for access.
- The old conclusion here — "raw S bytes work on real Net/ZNet hardware" — was a
  v1 observation generalised to v2/ZNet. It was wrong and has been removed.

The decompiler output is Telldus' Python 2.7 source. Keep it out of the repo
(`znet-decompile/` is git-ignored).
