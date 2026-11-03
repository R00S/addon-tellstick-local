#!/usr/bin/env bash
#
# Tests /etc/tellstick.conf generation in
# tellsticklive/rootfs/etc/cont-init.d/telldusd.sh without bashio, telldusd or
# root access.
#
# The bashio functions the script calls are stubbed with jq lookups over a test
# config, and only the CONFIG= line of a temporary copy is redirected at a temp
# file. This is regression cover for #127/#128: devices whose parameters are
# missing from the app config used to be written with literal "null" values, so
# code-switch devices such as sartano lost their code and several of them
# collapsed into one `sartano_selflearning_null_null` entry.
#
# Usage: bash tests/test_app_config_devices.sh

set -uo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPT="${REPO_ROOT}/tellsticklive/rootfs/etc/cont-init.d/telldusd.sh"

WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT

TEST_CONF="${WORK}/tellstick.conf"
SCRIPT_COPY="${WORK}/telldusd.sh"
CONFIG_JSON="${WORK}/config.json"

ALL_PASS=true

pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; ALL_PASS=false; }

expect_contains() {
    if grep -qF -- "$2" <<<"$1"; then
        pass "$3"
    else
        fail "$3 (missing '$2')"
    fi
}

expect_missing() {
    if grep -qF -- "$2" <<<"$1"; then
        fail "$3 (found '$2')"
    else
        pass "$3"
    fi
}

expect_count() {
    local actual
    actual=$(grep -cF -- "$2" <<<"$1" || true)
    if [[ "${actual}" == "$3" ]]; then
        pass "$4"
    else
        fail "$4 (expected $3 x '$2', got ${actual})"
    fi
}

# --- bashio stubs -----------------------------------------------------------
# bashio::config returns "null" for a missing option, exactly like the real
# implementation; bashio::config.has_value is false for that string.
bashio::log.info() { :; }

bashio::var.has_value() { [[ -n "${1}" ]]; }

bashio::config() {
    local key="$1"
    if [[ "${key}" == *'|keys' ]]; then
        jq -r '.devices | keys_unsorted[]' "${CONFIG_JSON}"
        return 0
    fi
    jq -r --arg k "${key}" '
        ($k | capture("devices\\[(?<i>[0-9]+)\\]\\.(?<f>.+)")) as $m
        | (.devices[($m.i | tonumber)][$m.f]) as $v
        | if $v == null then "null" else ($v | tostring) end
    ' "${CONFIG_JSON}"
}

bashio::config.has_value() {
    local value
    value=$(bashio::config "$1")
    [[ "${value}" != "null" && -n "${value}" ]]
}

# Run the generator against a config and print the generated file.
run_case() {
    printf '%s\n' "$1" > "${CONFIG_JSON}"
    (source "${SCRIPT_COPY}") >/dev/null
    cat "${TEST_CONF}"
}

sed 's|^CONFIG="/etc/tellstick.conf"$|CONFIG="${TEST_CONF}"|' "${SCRIPT}" > "${SCRIPT_COPY}"

if ! grep -q 'CONFIG="${TEST_CONF}"' "${SCRIPT_COPY}"; then
    echo "could not redirect CONFIG in the script copy" >&2
    exit 2
fi

if ! command -v jq >/dev/null; then
    echo "jq is required" >&2
    exit 2
fi

# --- Case 1: sartano with a code and no house/unit -------------------------
echo "=== Case 1: sartano device keeps its code ==="
OUT=$(run_case '{"devices":[{"id":1,"name":"Sartano A","protocol":"sartano","model":"codeswitch","code":"123456"}]}')
expect_contains "${OUT}" 'code = "123456"' 'code is written'
expect_missing "${OUT}" 'null' 'no literal null parameter'
expect_missing "${OUT}" 'house =' 'missing house is not written'

# --- Case 2: two sartano devices do not collapse into one ------------------
echo ""
echo "=== Case 2: two sartano devices stay distinct ==="
OUT=$(run_case '{"devices":[{"id":1,"name":"Sartano A","protocol":"sartano","model":"codeswitch","code":"111111"},{"id":2,"name":"Sartano B","protocol":"sartano","model":"codeswitch","code":"222222"}]}')
expect_count "${OUT}" 'device {' 2 'both device blocks are written'
expect_contains "${OUT}" 'code = "111111"' 'first code is written'
expect_contains "${OUT}" 'code = "222222"' 'second code is written'
expect_missing "${OUT}" 'null' 'no literal null parameter'

# --- Case 3: arctech house/unit still works --------------------------------
echo ""
echo "=== Case 3: arctech house/unit unchanged ==="
OUT=$(run_case '{"devices":[{"id":1,"name":"Lamp","protocol":"arctech","model":"selflearning-switch","house":"12345678","unit":"1"}]}')
expect_contains "${OUT}" 'house = "12345678"' 'house is written'
expect_contains "${OUT}" 'unit = "1"' 'unit is written'
expect_missing "${OUT}" 'code =' 'missing code is not written'

# --- Case 4: device with no parameters at all ------------------------------
echo ""
echo "=== Case 4: device without parameters writes no nulls ==="
OUT=$(run_case '{"devices":[{"id":1,"name":"Bare","protocol":"arctech","model":"selflearning-switch"}]}')
expect_missing "${OUT}" 'null' 'no literal null parameter'
expect_contains "${OUT}" 'name = "Bare"' 'device itself is still written'

echo ""
echo "=================================================="
if [[ "${ALL_PASS}" == true ]]; then
    echo "ALL TESTS PASSED"
    echo "=================================================="
    exit 0
fi
echo "SOME TESTS FAILED"
echo "=================================================="
exit 1
