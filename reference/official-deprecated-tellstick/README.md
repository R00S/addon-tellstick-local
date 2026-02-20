# Reference: Official Deprecated TellStick Add-on

This directory contains reference code from the deprecated official Home Assistant
TellStick add-on for comparison purposes.

## Source

Fork maintained at: https://github.com/Fufs/homeassistant-addons/tree/master/tellstick

The official add-on was deprecated because the telldus library is no longer maintained
by the manufacturer.

## Key Differences from This Add-on

### Socket/Service Startup Order

**Deprecated Official Add-on (run.sh):**

```bash
# Expose the unix socket to internal network
socat TCP-LISTEN:50800,reuseaddr,fork UNIX-CONNECT:/tmp/TelldusClient &
socat TCP-LISTEN:50801,reuseaddr,fork UNIX-CONNECT:/tmp/TelldusEvents &

# Run telldus-core daemon in the background
/usr/local/sbin/telldusd --nodaemon < /dev/null &
```

- socat starts BEFORE telldusd
- Race condition: socat tries to connect to sockets that may not exist yet
- Each incoming TCP connection forks and tries to connect to UNIX socket
- First connection after startup may fail if telldusd hasn't created sockets yet

**This Fork (telldusd/run):**

```bash
# Start telldusd in the background first so it creates the UNIX sockets
/usr/local/sbin/telldusd --nodaemon &

# Wait for telldusd to create the UNIX sockets
while [[ ! -S /tmp/TelldusClient ]] || [[ ! -S /tmp/TelldusEvents ]]; do
    sleep 1
done

# Then start socat
socat TCP-LISTEN:50800,reuseaddr,fork UNIX-CONNECT:/tmp/TelldusClient &
socat TCP-LISTEN:50801,reuseaddr,fork UNIX-CONNECT:/tmp/TelldusEvents &
```

- telldusd starts FIRST
- Script waits for UNIX sockets to be created (up to 60 seconds)
- socat only starts after sockets are ready
- More reliable startup sequence

### Service Architecture

**Deprecated Official Add-on:**

- Single script (run.sh) that does everything
- No S6 service supervision
- stdin handling in main script

**This Fork:**

- S6 overlay with separate services:
  - `telldusd/run` - Main TellStick daemon and socat bridges
  - `tellivecore/run` - Telldus Live connector (optional)
  - `runonce/run` - Initial Telldus Live registration
  - `stdin/run` - Home Assistant stdin service calls
- Proper service isolation and restart handling

### Telldus Live Support

**Deprecated Official Add-on:**

- No Telldus Live support

**This Fork:**

- Full Telldus Live integration
- UUID-based authentication
- Cloud-based device control option
