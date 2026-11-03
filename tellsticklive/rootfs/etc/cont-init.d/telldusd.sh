#!/command/with-contenv bashio

# This script will create the config file needed to connect to start telldusd

CONFIG="/etc/tellstick.conf"

bashio::log.info "Initialize the tellstick configuration..."
# User access
{
    echo "user = \"root\""
    echo "group = \"plugdev\""
    echo "ignoreControllerConfirmation = \"false\"" 
} > "${CONFIG}"

# devices
for device in $(bashio::config 'devices|keys'); do
    DEV_ID=$(bashio::config "devices[${device}].id")
    DEV_NAME=$(bashio::config "devices[${device}].name")
    DEV_PROTO=$(bashio::config "devices[${device}].protocol")
    DEV_MODEL=$(bashio::config "devices[${device}].model")
    ATTR_HOUSE=$(bashio::config "devices[${device}].house")
    ATTR_CODE=$(bashio::config "devices[${device}].code")
    ATTR_UNIT=$(bashio::config "devices[${device}].unit")
    ATTR_FADE=$(bashio::config "devices[${device}].fade")
  
    (
        echo ""
        echo "device {"
        echo "  id = ${DEV_ID}"
        echo "  name = \"${DEV_NAME}\""
        echo "  protocol = \"${DEV_PROTO}\""
        
        bashio::var.has_value "${DEV_MODEL}" \
            && echo "  model = \"${DEV_MODEL}\""
        
        if bashio::var.has_value "${ATTR_HOUSE}${ATTR_CODE}${ATTR_UNIT}${ATTR_FADE}";
        then
            echo "  parameters {"

            bashio::config.has_value "devices[${device}].house" \
                && echo "    house = \"${ATTR_HOUSE}\""

            bashio::config.has_value "devices[${device}].code" \
                && echo "    code = \"${ATTR_CODE}\""

            bashio::config.has_value "devices[${device}].unit" \
                && echo "    unit = \"${ATTR_UNIT}\""

            bashio::config.has_value "devices[${device}].fade" \
                && echo "    fade = \"${ATTR_FADE}\""
            
            echo "  }"
        fi
        
        echo "}"
    ) >> "${CONFIG}"
done
