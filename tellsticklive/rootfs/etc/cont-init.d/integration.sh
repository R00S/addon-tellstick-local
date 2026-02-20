#!/command/with-contenv bashio

# Install the companion integration into HA custom_components so that
# the Supervisor discovery prompt works without a separate HACS install.

SRC="/usr/share/tellstick_local"
DEST="/config/custom_components/tellstick_local"

if [[ ! -d "${SRC}" ]]; then
    bashio::log.warning "Integration source not found at ${SRC}, skipping install"
    exit 0
fi

bashio::log.info "Installing TellStick Local integration to ${DEST}..."
mkdir -p "${DEST}"
cp -rf "${SRC}/." "${DEST}/"
bashio::log.info "TellStick Local integration installed."
