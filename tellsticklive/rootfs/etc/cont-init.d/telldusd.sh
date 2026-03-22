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

            bashio::var.has_value "${ATTR_HOUSE}" \
                && echo "    house = \"${ATTR_HOUSE}\""

            bashio::var.has_value "${ATTR_CODE}" \
                && echo "    code = \"${ATTR_CODE}\""

            bashio::var.has_value "${ATTR_UNIT}" \
                && echo "    unit = \"${ATTR_UNIT}\""

            bashio::var.has_value "${ATTR_FADE}" \
                && echo "    fade = \"${ATTR_FADE}\""
            
            echo "  }"
        fi
        
        echo "}"
    ) >> "${CONFIG}"
done

# Network controller (TellStick Net / ZNet)
CONTROLLER_TYPE=$(bashio::config 'controller_type' 'usb')
CONTROLLER_IP=$(bashio::config 'controller_ip' '')

if [[ "${CONTROLLER_TYPE}" != "usb" ]] && bashio::var.has_value "${CONTROLLER_IP}"; then
    # Map config value → telldusd type string
    if [[ "${CONTROLLER_TYPE}" == "net" ]]; then
        TD_TYPE="TellStickNet"
    elif [[ "${CONTROLLER_TYPE}" == "znet" ]]; then
        TD_TYPE="TellStickZNet"
    else
        bashio::log.warning "Unknown controller_type '${CONTROLLER_TYPE}', skipping network controller configuration"
        TD_TYPE=""
    fi
    if bashio::var.has_value "${TD_TYPE}"; then
        bashio::log.info "Configuring network controller: type=${TD_TYPE} ip=${CONTROLLER_IP}"
        {
            echo ""
            echo "controller {"
            echo "  id = 1"
            echo "  type = \"${TD_TYPE}\""
            echo "  ip = \"${CONTROLLER_IP}\""
            echo "}"
        } >> "${CONFIG}"
    fi
fi
