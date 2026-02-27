#!/command/with-contenv bashio

# Install or update the companion integration in HA custom_components.
# - First install: copies files so Supervisor discovery can trigger the "Set up?" prompt.
# - Update: copies new files. The integration's own version-mismatch check
#   (in __init__.py) will raise a HA repair issue prompting the user to restart.
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

if [[ "${INSTALLED_VERSION}" != "none" ]]; then
    # Write a sentinel so _check_version_mismatch() can fire the right notice:
    #   - On cold boot (full restart): sentinel version == new INTEGRATION_VERSION
    #     → "update applied" informational notification, sentinel deleted.
    #   - On hot reload (app restarted, HA kept running): sentinel version !=
    #     old INTEGRATION_VERSION in memory → "restart required" repair issue.
    echo "${BUNDLED_VERSION}" > "${DEST}/.pending_update"
    bashio::log.info "Integration updated from v${INSTALLED_VERSION} to v${BUNDLED_VERSION} — update sentinel written."
    # Also trigger a config-entry reload so HA fires the "restart required"
    # notice immediately if it is still running with old code in memory
    # (hot-update scenario: app restarted, HA Core kept running).
    ENTRIES_JSON=$(curl -sf \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/core/api/config/config_entries" 2>/dev/null || true)
    if [[ -z "${ENTRIES_JSON}" ]]; then
        bashio::log.warning "Could not reach HA API — notice will appear after next HA restart"
    else
        ENTRY_IDS=$(jq -r '.[] | select(.domain == "tellstick_local") | .entry_id' \
            <<< "${ENTRIES_JSON}" 2>/dev/null || true)
        if [[ -n "${ENTRY_IDS}" ]]; then
            while IFS= read -r ENTRY_ID; do
                HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
                    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
                    "http://supervisor/core/api/config/config_entries/${ENTRY_ID}/reload" \
                    2>/dev/null || echo "000")
                if [[ "${HTTP_STATUS}" == "200" ]]; then
                    bashio::log.info "Config entry ${ENTRY_ID} reloaded — restart required notice now visible"
                else
                    bashio::log.warning "Could not reload config entry ${ENTRY_ID} (HTTP ${HTTP_STATUS}) — notice will appear after next HA restart"
                fi
            done <<< "${ENTRY_IDS}"
        else
            bashio::log.info "No active TellStick Local config entry found — notice will appear after next HA restart"
        fi
    fi
fi
