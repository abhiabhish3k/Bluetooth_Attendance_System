/**
 * Device Parser – MAC address/RSSI validation and beacon data parsing.
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
// parseBeaconId
//
// Supported formats:
//
//  1. Apple iBeacon (companyId == 0x004C)
//     payload: [0x02][0x15][16-byte UUID][2-byte major BE][2-byte minor BE][1-byte tx]
//     → returns "<major>:<minor>" (decimal)
//
//  2. Custom BLE-Attendance (companyId == 0xFFFF)
//     payload: [0x42][0x41][len][utf8 bytes…]
//     → returns the embedded unique_id string
// ---------------------------------------------------------------------------
std::string DeviceParser::parseBeaconId(uint16_t companyId,
                                         const std::vector<uint8_t>& payload) {
    if (companyId == IBEACON_COMPANY_ID) {
        // Need at least IBEACON_PAYLOAD_SIZE bytes
        if (payload.size() < IBEACON_PAYLOAD_SIZE) return {};
        if (payload[0] != IBEACON_SUBTYPE)     return {};
        if (payload[1] != IBEACON_SUBTYPE_LEN) return {};

        // Major at bytes 18–19 (big-endian), minor at bytes 20–21 (big-endian)
        // UUID occupies bytes 2–17
        uint16_t major = (static_cast<uint16_t>(payload[18]) << 8) |
                          static_cast<uint16_t>(payload[19]);
        uint16_t minor = (static_cast<uint16_t>(payload[20]) << 8) |
                          static_cast<uint16_t>(payload[21]);

        std::ostringstream oss;
        oss << major << ":" << minor;
        return oss.str();
    }

    if (companyId == CUSTOM_COMPANY_ID) {
        // Need magic bytes + length byte
        if (payload.size() < CUSTOM_MIN_PAYLOAD) return {};
        if (payload[0] != CUSTOM_MAGIC_0) return {};
        if (payload[1] != CUSTOM_MAGIC_1) return {};

        uint8_t len = payload[2];
        if (len == 0 || payload.size() < static_cast<size_t>(3 + len)) return {};

        // Limit to CUSTOM_MAX_UID_LENGTH characters
        size_t actualLen = std::min(static_cast<size_t>(len), CUSTOM_MAX_UID_LENGTH);
        std::string uid(reinterpret_cast<const char*>(payload.data() + 3), actualLen);

        // Ensure printable ASCII / valid UTF-8 (strip control chars)
        std::string safe;
        safe.reserve(uid.size());
        for (unsigned char c : uid) {
            if (c >= 0x20) safe.push_back(static_cast<char>(c));
        }
        return safe;
    }

    return {};
}

// ---------------------------------------------------------------------------
// buildEvent
// ---------------------------------------------------------------------------
std::optional<DeviceEvent> DeviceParser::buildEvent(const std::string& address,
                                                      const std::string& name,
                                                      int rssi,
                                                      int64_t timestamp,
                                                      const std::string& beacon_id) {
    if (!validateMac(address))  return std::nullopt;
    if (!validateRssi(rssi))    return std::nullopt;
    if (timestamp <= 0)         return std::nullopt;

    DeviceEvent ev;
    ev.address   = address;
    ev.name      = sanitiseName(name);
    ev.rssi      = rssi;
    ev.timestamp = timestamp;
    ev.beacon_id = beacon_id;
    return ev;
}

} // namespace ble
