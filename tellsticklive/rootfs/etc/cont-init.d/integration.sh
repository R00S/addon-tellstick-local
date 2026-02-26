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
    bashio::log.info "Integration updated from v${INSTALLED_VERSION} to v${BUNDLED_VERSION} — reloading config entry so HA raises a repair issue..."
    # Trigger a config-entry reload so that _check_version_mismatch() in
    # __init__.py runs while the OLD code is still in memory.  The reload:
    #   1. reads the new on-disk manifest.json (new version)
    #   2. compares it to INTEGRATION_VERSION frozen at HA startup (old version)
    #   3. calls async_create_issue → appears in Settings → Repairs
    # After the user restarts HA the new code is loaded, versions match, and
    # async_delete_issue clears the repair item automatically.
    ENTRIES_JSON=$(curl -sf \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/core/api/config/config_entries" 2>/dev/null || true)
    if [[ -z "${ENTRIES_JSON}" ]]; then
        bashio::log.warning "Could not reach HA API — repair issue will appear after next HA restart"
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
                    bashio::log.info "Config entry ${ENTRY_ID} reloaded — repair issue now visible in Settings → Repairs"
                else
                    bashio::log.warning "Could not reload config entry ${ENTRY_ID} (HTTP ${HTTP_STATUS}) — repair issue will appear after next HA restart"
                fi
            done <<< "${ENTRY_IDS}"
        else
            bashio::log.info "No active TellStick Local config entry found — repair issue will appear after next HA restart"
        fi
    fi
fi
