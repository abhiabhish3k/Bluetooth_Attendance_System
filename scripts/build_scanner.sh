#!/usr/bin/env bash
# =============================================================================
# build_scanner.sh – Compile the C++ BLE scanner
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCANNER_DIR="$REPO_ROOT/scanner"
BUILD_DIR="$SCANNER_DIR/build"

echo "==> Installing system dependencies (requires sudo)..."
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y \
        build-essential cmake pkg-config \
        libbluetooth-dev libdbus-1-dev libglib2.0-dev \
        bluez
elif command -v dnf &>/dev/null; then
    sudo dnf install -y cmake gcc-c++ pkg-config \
        bluez-libs-devel dbus-devel glib2-devel
else
    echo "WARNING: Unknown package manager – skipping dependency install."
    echo "Please ensure the following are installed:"
    echo "  cmake, g++, pkg-config, libbluetooth-dev, libdbus-1-dev, libglib2.0-dev"
fi

echo "==> Configuring build..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake .. -DCMAKE_BUILD_TYPE=Release

echo "==> Compiling..."
make -j"$(nproc)"

echo ""
echo "Build complete!"
echo "Binary: $BUILD_DIR/bin/ble_scanner"
echo ""
echo "To run the scanner:"
echo "  sudo $BUILD_DIR/bin/ble_scanner $SCANNER_DIR/config.json"
