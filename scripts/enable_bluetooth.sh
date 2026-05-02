#!/usr/bin/env bash
# =============================================================================
# enable_bluetooth.sh – Power on the Bluetooth adapter for BLE scanning
#
# Usage:
#   bash scripts/enable_bluetooth.sh           # use default adapter (hci0)
#   BT_ADAPTER=hci1 bash scripts/enable_bluetooth.sh
#
# The script tries the following methods in order:
#   1. sudo hciconfig <adapter> up
#   2. sudo bluetoothctl power on
#   3. sudo systemctl restart bluetooth  (last resort)
#
# Run this script before starting the backend if the scanner is failing with:
#   [BleScanner] StartDiscovery error: Resource Not Ready
# =============================================================================
set -uo pipefail

ADAPTER="${BT_ADAPTER:-hci0}"

echo "==> Enabling Bluetooth adapter: $ADAPTER"
echo ""

# ---------------------------------------------------------------------------
# Check current state
# ---------------------------------------------------------------------------
POWERED_PATH="/sys/class/bluetooth/$ADAPTER/powered"
if [[ ! -d "/sys/class/bluetooth/$ADAPTER" ]]; then
    echo "[WARN] Adapter '$ADAPTER' not found in sysfs."
    echo "       Available adapters:"
    ls /sys/class/bluetooth/ 2>/dev/null || echo "         (none found)"
    echo ""
    echo "       If you have a different adapter, set BT_ADAPTER=<name> and re-run."
    echo "       Also check that the bluetooth service is running:"
    echo "         sudo systemctl status bluetooth"
    echo "         sudo systemctl start bluetooth"
    exit 1
fi

if [[ -f "$POWERED_PATH" ]] && [[ "$(cat "$POWERED_PATH" 2>/dev/null)" == "1" ]]; then
    echo "==> Adapter '$ADAPTER' is already powered on."
    exit 0
fi

echo "    Adapter '$ADAPTER' is present but not powered on – attempting to power it on..."
echo ""

# ---------------------------------------------------------------------------
# Method 1: hciconfig
# ---------------------------------------------------------------------------
if command -v hciconfig &>/dev/null; then
    echo "--- Trying: sudo hciconfig $ADAPTER up"
    if sudo hciconfig "$ADAPTER" up 2>&1; then
        echo ""
        # Give adapter a moment to initialise
        sleep 1
        if [[ -f "$POWERED_PATH" ]] && [[ "$(cat "$POWERED_PATH" 2>/dev/null)" == "1" ]]; then
            echo "==> SUCCESS: Adapter '$ADAPTER' is now powered on via hciconfig."
            exit 0
        else
            echo "    hciconfig returned success but adapter not yet reporting powered state."
        fi
    else
        echo "    hciconfig failed."
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# Method 2: bluetoothctl
# ---------------------------------------------------------------------------
if command -v bluetoothctl &>/dev/null; then
    echo "--- Trying: sudo bluetoothctl power on"
    if sudo bluetoothctl power on 2>&1; then
        sleep 1
        if [[ -f "$POWERED_PATH" ]] && [[ "$(cat "$POWERED_PATH" 2>/dev/null)" == "1" ]]; then
            echo "==> SUCCESS: Adapter '$ADAPTER' is now powered on via bluetoothctl."
            exit 0
        else
            echo "    bluetoothctl returned success but adapter not yet reporting powered state."
        fi
    else
        echo "    bluetoothctl failed."
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# Method 3: restart bluetooth service
# ---------------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
    echo "--- Trying: sudo systemctl restart bluetooth"
    if sudo systemctl restart bluetooth 2>&1; then
        sleep 2
        if [[ -f "$POWERED_PATH" ]] && [[ "$(cat "$POWERED_PATH" 2>/dev/null)" == "1" ]]; then
            echo "==> SUCCESS: Adapter '$ADAPTER' is now powered on after service restart."
            exit 0
        else
            echo "    Service restarted but adapter still not powered."
            echo "    Try: sudo hciconfig $ADAPTER up  after the service finishes starting."
        fi
    else
        echo "    systemctl restart bluetooth failed."
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# All methods failed
# ---------------------------------------------------------------------------
echo "ERROR: Could not power on Bluetooth adapter '$ADAPTER' automatically."
echo ""
echo "Manual steps to fix:"
echo "  1. Check the Bluetooth service:"
echo "       sudo systemctl status bluetooth"
echo "       sudo systemctl start bluetooth"
echo ""
echo "  2. Power on the adapter:"
echo "       sudo hciconfig $ADAPTER up"
echo "       # or"
echo "       sudo bluetoothctl power on"
echo ""
echo "  3. Verify the adapter is ready:"
echo "       hciconfig $ADAPTER"
echo "       cat /sys/class/bluetooth/$ADAPTER/powered   # should print 1"
echo ""
echo "  4. If using a USB Bluetooth dongle, replug it and retry."
echo ""
echo "  5. Check D-Bus permissions (add user to bluetooth group):"
echo "       sudo usermod -aG bluetooth \$USER"
echo "       # Then log out and log back in"
exit 1
