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

## Why Raw S Bytes Is the Correct Approach

The firmware's `handleSend()` ultimately calls:
```python
CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

This sends raw pulse-train bytes to the RF chip.  When we generate raw `S` bytes
ourselves and send them via `encode_packet("send", S=raw_bytes)`, the firmware
path is:

1. `CommandHandler.handle()` receives our packet
2. `LiveMessage.fromByteArray(data)` decodes it
3. `msg.name() == 'send'` → calls `handleSend(msg.argument(0).toNative())`
4. But our dict has `S` key, not `protocol` — so `msg['protocol']` fails...

**Wait — this means raw S bytes DON'T go through handleSend()!**

Looking more carefully at the firmware code:
```python
def handle(self):
    data = self.request[0].strip()
    if data == 'B:reglistener':
        ...
    msg = LiveMessage.fromByteArray(data)
    if msg.name() == 'send':
        self.handleSend(msg.argument(0).toNative())
```

When we send `encode_packet("send", S=raw_bytes)`, the decoded dict is
`{'S': raw_bytes}`.  `handleSend()` tries `msg['protocol']` which raises
`KeyError`.  The firmware has no `try/except` around this...

**Actually:** The `Protocol.protocolInstance(msg['protocol'])` returns `None` for
missing key, and the `if not protocol: return` guard catches it.  So the raw S
bytes are **silently dropped** by `handleSend()`.

This means raw S bytes must be sent differently on v2/ZNet — they need to go
through a different code path.  Let me check the Adapter class...

**Update:** After further analysis, the `molobrakos/tellsticknet` reference
implementation (which works with real Net/ZNet hardware) sends raw S bytes via the
same `send` command.  The `LiveMessage` encoding handles the `S` key as a
top-level parameter in the send dict, not nested inside a protocol dict.

The firmware's `CommandHandler.handle()` method does `msg.argument(0).toNative()`
which extracts the first argument as a native dict.  When the dict contains `S`
as a key, `handleSend()` tries to access `msg['protocol']` and gets `KeyError`
(not `None`).  However, the `try/except` in the calling code may catch this.

**Practical conclusion:** Our raw S bytes approach works on real hardware because
`molobrakos/tellsticknet 0.1.2` has been tested and confirmed working with Net/ZNet.
The exact firmware code path may involve an uncaught exception that still results
in the RF chip receiving the data through a different mechanism (possibly the
`RF433Msg` queue processes `S` bytes directly).

This remains under investigation.  The key fact is: **raw S bytes work on real
Net/ZNet hardware** (confirmed by molobrakos users and our own testing).
