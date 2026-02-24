#!/command/with-contenv bashio

# Install or update the companion integration in HA custom_components.
# - First install: copies files so Supervisor discovery can trigger the "Set up?" prompt.
# - Update: copies new files and sends a persistent notification asking
#   the user to restart HA Core (which caches Python modules in memory).
# - No change: skips copy to avoid unnecessary disruption.

SRC="/usr/share/tellstick_local"
DEST="/homeassistant/custom_components/tellstick_local"

if [[ ! -d "${SRC}" ]]; then
    bashio::log.warning "Integration source not found at ${SRC}, skipping install"
    exit 0
fi

# Read versions for change detection
BUNDLED_VERSION=$(jq -r '.version' "${SRC}/manifest.json" 2>/dev/null || echo "unknown")
INSTALLED_VERSION=$(jq -r '.version' "${DEST}/manifest.json" 2>/dev/null || echo "none")

if [[ "${BUNDLED_VERSION}" == "${INSTALLED_VERSION}" ]]; then
    bashio::log.info "TellStick Local integration v${INSTALLED_VERSION} already up to date, skipping install"
    exit 0
fi

bashio::log.info "Installing TellStick Local integration v${BUNDLED_VERSION} (was: ${INSTALLED_VERSION})..."
mkdir -p "${DEST}"
cp -rf "${SRC}/." "${DEST}/"
bashio::log.info "TellStick Local integration v${BUNDLED_VERSION} installed."

# If HA Core is already running (i.e. this is an update, not first boot),
# notify the user that a restart is needed to load the new integration code.
# We no longer auto-restart HA Core — that was disruptive and could interrupt
# automations.  The integration itself also detects the version mismatch at
# next setup and shows the same notification.
if [[ "${INSTALLED_VERSION}" != "none" ]]; then
    bashio::log.info "Integration updated — notifying user to restart HA Core..."
    # Use the Supervisor API proxy to create a persistent notification in HA.
    # Requires homeassistant_api: true in config.yaml.
    if curl -s -X POST \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"title\":\"TellStick Local — restart required\",\"message\":\"The TellStick Local app installed integration **v${BUNDLED_VERSION}** (previously v${INSTALLED_VERSION}).\\n\\n**Restart Home Assistant** to activate the new version.\\n\\nGo to **Settings → System → Restart**.\",\"notification_id\":\"tellstick_local_update\"}" \
        "http://supervisor/core/api/services/persistent_notification/create" \
        > /dev/null 2>&1; then
        bashio::log.info "Persistent notification sent — user will be prompted to restart HA"
    else
        bashio::log.warning "Could not send notification — please restart Home Assistant manually to load TellStick Local v${BUNDLED_VERSION}"
    fi
fi
