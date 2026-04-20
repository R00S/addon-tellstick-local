#!/command/with-contenv bashio

# Install or update the companion integration in HA custom_components.
# - First install: copies files so Supervisor discovery can trigger the "Set up?" prompt.
# - Update: copies new files, then automatically restarts HA Core via the Supervisor API
#   so the new integration code is loaded without the user needing to restart manually.
#   (HAOS starts HA Core before add-on containers, so without this restart HA would be
#   left running the old integration code.)
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
    # HAOS starts HA Core before add-on containers, so HA will have already
    # loaded the OLD integration by the time this script runs.  Instead of
    # prompting the user to restart manually, automatically restart HA Core
    # via the Supervisor API so the new integration is loaded transparently.
    bashio::log.info "Integration updated from v${INSTALLED_VERSION} to v${BUNDLED_VERSION} — restarting HA Core to activate new version..."
    HA_RESTART_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/core/restart" 2>/dev/null || echo "000")
    if [[ "${HA_RESTART_STATUS}" == "200" ]]; then
        bashio::log.info "HA Core restart triggered — TellStick Local v${BUNDLED_VERSION} will be active after restart"
    else
        # Auto-restart failed — fall back to notifying the user manually.
        bashio::log.warning "Could not restart HA Core (HTTP ${HA_RESTART_STATUS}) — notifying user to restart manually"
        curl -s -X POST \
            -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"title\":\"TellStick Local — restart required\",\"message\":\"The TellStick Local app installed integration **v${BUNDLED_VERSION}** (previously v${INSTALLED_VERSION}).\\n\\n**Restart Home Assistant** to activate the new version.\\n\\nGo to **Settings → Developer tools → Restart**.\",\"notification_id\":\"restart_required\"}" \
            "http://supervisor/core/api/services/persistent_notification/create" \
            > /dev/null 2>&1 || true
        # Also reload the config entry so the repair issue fires immediately.
        ENTRIES_JSON=$(curl -sf \
            -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
            "http://supervisor/core/api/config/config_entries" 2>/dev/null || true)
        if [[ -n "${ENTRIES_JSON}" ]]; then
            ENTRY_IDS=$(jq -r '.[] | select(.domain == "tellstick_local") | .entry_id' \
                <<< "${ENTRIES_JSON}" 2>/dev/null || true)
            if [[ -n "${ENTRY_IDS}" ]]; then
                while IFS= read -r ENTRY_ID; do
                    curl -s -o /dev/null -X POST \
                        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
                        "http://supervisor/core/api/config/config_entries/${ENTRY_ID}/reload" \
                        2>/dev/null || true
                done <<< "${ENTRY_IDS}"
            fi
        fi
    fi
fi
