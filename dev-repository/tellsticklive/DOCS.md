# TellStick Local — Dev Channel

> ⚠️ **You are on the development channel** (`addon-tellsticklive-roosfork`).
>
> This channel receives the latest unreleased features and may occasionally be
> unstable. If you just want a reliable TellStick setup, switch to the
> **stable channel** — it takes less than a minute.

---

## How to switch to the stable channel

1. In HAOS go to **Settings → Apps → ⋮ → Repositories**
2. **Remove** `https://github.com/R00S/addon-tellsticklive-roosfork`
3. **Add** `https://github.com/R00S/addon-tellstick-local`, category **App**
4. Find **TellStick Local** in the app store and click **Install**

Your existing configuration is preserved — the slug is identical, so HAOS
treats the stable app as an update to the one already installed.

---

## Why am I on the dev channel?

You were probably on the original `addon-tellsticklive-roosfork` repository
before this project split into a stable and a dev channel. To avoid
orphaning existing users, the old repository URL was kept for the dev channel.

The integration itself will also show a warning in
**Settings → Repairs** as long as you are on the dev channel.

---

## About this app

See the [main project README](https://github.com/R00S/addon-tellstick-local)
for full installation and usage instructions, supported devices, and troubleshooting.

This app runs the Telldus `telldusd` daemon inside a Docker container and exposes
it over TCP:

- **Port 50800** – command socket (turn on/off, dim)
- **Port 50801** – event socket (real-time RF events from remotes and sensors)

---

## Support

- [Open an issue on GitHub](https://github.com/R00S/addon-tellstick-local/issues)

## License

GNU General Public License v3.0 or later
