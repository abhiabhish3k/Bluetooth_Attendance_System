#pragma once

#include <string>
#include <optional>
#include "ble_scanner.h"

namespace ble {

/**
 * Utilities for parsing and validating BLE device data.
 */
class DeviceParser {
public:
    /**
     * Convert a BlueZ D-Bus object path to a standard MAC address string.
     *
     * Example:
     *   "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF" -> "AA:BB:CC:DD:EE:FF"
     *
     * @param objectPath D-Bus object path for the device.
     * @return MAC address string, or empty string if the path is invalid.
     */
    static std::string extractMacFromPath(const std::string& objectPath);

    /**
     * Validate that a MAC address string is well-formed.
     *
     * Accepts format: "XX:XX:XX:XX:XX:XX" where X is a hex digit.
     *
     * @param mac MAC address to validate.
     * @return true if valid, false otherwise.
     */
    static bool validateMac(const std::string& mac);

    /**
     * Validate that an RSSI value is within the physically meaningful range.
     *
     * Valid range: -120 dBm to +10 dBm.
     *
     * @param rssi RSSI value in dBm.
     * @return true if in valid range, false otherwise.
     */
    static bool validateRssi(int rssi);

    /**
     * Sanitise a device name (strip control characters, limit length).
     *
     * @param raw Raw device name from advertisement.
     * @return Sanitised name (may be empty if raw was empty or only whitespace).
     */
    static std::string sanitiseName(const std::string& raw);

    /**
     * Build a DeviceEvent from raw components, validating each field.
     *
     * @param address      MAC address string.
     * @param name         Device name (may be empty).
     * @param rssi         RSSI value.
     * @param timestamp    Unix timestamp.
     * @return DeviceEvent on success, std::nullopt if validation fails.
     */
    static std::optional<DeviceEvent> buildEvent(const std::string& address,
                                                  const std::string& name,
                                                  int rssi,
                                                  int64_t timestamp);

    static constexpr int MIN_RSSI = -120; ///< Minimum valid RSSI (dBm)
    static constexpr int MAX_RSSI =   10; ///< Maximum valid RSSI (dBm)
    static constexpr size_t MAX_NAME_LENGTH = 128; ///< Maximum device name length
};

} // namespace ble
