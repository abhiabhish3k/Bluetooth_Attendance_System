/**
 * Device Parser – MAC address and RSSI validation/parsing.
 */

#include "device_parser.h"

#include <algorithm>
#include <regex>
#include <sstream>
#include <iomanip>
#include <cctype>

namespace ble {

// ---------------------------------------------------------------------------
// extractMacFromPath
// "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF" → "AA:BB:CC:DD:EE:FF"
// ---------------------------------------------------------------------------
std::string DeviceParser::extractMacFromPath(const std::string& objectPath) {
    // Find the last component after '/'
    auto pos = objectPath.rfind('/');
    if (pos == std::string::npos) return {};

    std::string last = objectPath.substr(pos + 1);

    // Must start with "dev_" and have the right length (dev_ + 5*3 + 2 = 20)
    // Format: dev_XX_XX_XX_XX_XX_XX  (17 chars after "dev_")
    static const std::string prefix = "dev_";
    if (last.size() < prefix.size() + 17) return {};
    if (last.substr(0, prefix.size()) != prefix) return {};

    std::string macPart = last.substr(prefix.size()); // "AA_BB_CC_DD_EE_FF"
    // Replace underscores with colons
    std::replace(macPart.begin(), macPart.end(), '_', ':');

    if (!validateMac(macPart)) return {};
    return macPart;
}

// ---------------------------------------------------------------------------
// validateMac
// ---------------------------------------------------------------------------
bool DeviceParser::validateMac(const std::string& mac) {
    // Expect exactly "XX:XX:XX:XX:XX:XX" (17 chars)
    if (mac.size() != 17) return false;

    for (size_t i = 0; i < mac.size(); ++i) {
        if (i % 3 == 2) {
            if (mac[i] != ':') return false;
        } else {
            if (!std::isxdigit(static_cast<unsigned char>(mac[i]))) return false;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// validateRssi
// ---------------------------------------------------------------------------
bool DeviceParser::validateRssi(int rssi) {
    return (rssi >= MIN_RSSI && rssi <= MAX_RSSI);
}

// ---------------------------------------------------------------------------
// sanitiseName
// ---------------------------------------------------------------------------
std::string DeviceParser::sanitiseName(const std::string& raw) {
    std::string out;
    out.reserve(raw.size());
    for (unsigned char c : raw) {
        if (c < 0x20 && c != '\t') continue; // strip control chars except tab
        out.push_back(static_cast<char>(c));
    }
    // Trim trailing whitespace
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) {
        out.pop_back();
    }
    if (out.size() > MAX_NAME_LENGTH) {
        out.resize(MAX_NAME_LENGTH);
    }
    return out;
}

// ---------------------------------------------------------------------------
// buildEvent
// ---------------------------------------------------------------------------
std::optional<DeviceEvent> DeviceParser::buildEvent(const std::string& address,
                                                      const std::string& name,
                                                      int rssi,
                                                      int64_t timestamp) {
    if (!validateMac(address))  return std::nullopt;
    if (!validateRssi(rssi))    return std::nullopt;
    if (timestamp <= 0)         return std::nullopt;

    DeviceEvent ev;
    ev.address   = address;
    ev.name      = sanitiseName(name);
    ev.rssi      = rssi;
    ev.timestamp = timestamp;
    return ev;
}

} // namespace ble
