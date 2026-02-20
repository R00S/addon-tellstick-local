#!/command/with-contenv bashio

# Install or update the companion integration in HA custom_components.
# - First install: copies files so Supervisor discovery can trigger the "Set up?" prompt.
# - Update: copies new files and requests a HA Core restart (HA caches code in memory).
# - No change: skips copy and restart to avoid unnecessary disruption.

SRC="/usr/share/tellstick_local"
DEST="/config/custom_components/tellstick_local"

if [[ ! -d "${SRC}" ]]; then
    bashio::log.warning "Integration source not found at ${SRC}, skipping install"
    exit 0
fi

# Read versions for change detection
BUNDLED_VERSION=$(grep -oP '"version":\s*"\K[^"]+' "${SRC}/manifest.json" 2>/dev/null || echo "unknown")
INSTALLED_VERSION=$(grep -oP '"version":\s*"\K[^"]+' "${DEST}/manifest.json" 2>/dev/null || echo "none")

if [[ "${BUNDLED_VERSION}" == "${INSTALLED_VERSION}" ]]; then
    bashio::log.info "TellStick Local integration v${INSTALLED_VERSION} already up to date, skipping install"
    exit 0
fi

bashio::log.info "Installing TellStick Local integration v${BUNDLED_VERSION} (was: ${INSTALLED_VERSION})..."
mkdir -p "${DEST}"
cp -rf "${SRC}/." "${DEST}/"
bashio::log.info "TellStick Local integration v${BUNDLED_VERSION} installed."

# If HA Core is already running (i.e. this is an update, not first boot),
# request a restart so it picks up the new integration code.
if [[ "${INSTALLED_VERSION}" != "none" ]]; then
    bashio::log.info "Requesting HA Core restart to load updated integration..."
    bashio::core.restart || bashio::log.warning "Could not request HA Core restart — please restart manually"
fi
