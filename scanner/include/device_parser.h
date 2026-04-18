#pragma once

#include <string>
#include <optional>
#include <vector>
#include "ble_scanner.h"

namespace ble {

/**
 * iBeacon manufacturer data layout (following the 2-byte company ID).
 *
 * BlueZ exposes ManufacturerData as dict<uint16, array<byte>> where the key
 * is the company ID in host byte order and the value is the payload after
 * the company ID bytes.
 *
 * For Apple iBeacon (company ID 0x004C) the payload is:
 *   [0x02] [0x15] [16-byte UUID] [2-byte major BE] [2-byte minor BE] [1-byte TX power]
 *  = 21 bytes total
 */
static constexpr uint16_t IBEACON_COMPANY_ID    = 0x004C;
static constexpr uint8_t  IBEACON_SUBTYPE        = 0x02;
static constexpr uint8_t  IBEACON_SUBTYPE_LEN    = 0x15; // 21 bytes following
static constexpr size_t   IBEACON_PAYLOAD_SIZE   = 23;   // subtype(1)+len(1)+UUID(16)+major(2)+minor(2)+tx(1)

/**
 * Custom BLE-Attendance beacon (company ID 0xFFFF, private use).
 *
 * Payload layout:
 *   [0x42][0x41] ("BA" magic)  2 bytes
 *   [length]                   1 byte  – number of UTF-8 bytes that follow
 *   [unique_id bytes]          up to 61 bytes
 */
static constexpr uint16_t CUSTOM_COMPANY_ID     = 0xFFFF;
static constexpr uint8_t  CUSTOM_MAGIC_0        = 0x42; // 'B'
static constexpr uint8_t  CUSTOM_MAGIC_1        = 0x41; // 'A'
static constexpr size_t   CUSTOM_MIN_PAYLOAD    = 3;    // magic(2) + length(1)

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
     * Try to parse a beacon identifier from raw manufacturer data bytes.
     *
     * Handles two formats:
     *   1. Apple iBeacon (company ID 0x004C): returns "<major>:<minor>" string.
     *   2. Custom BLE-Attendance format (company ID 0xFFFF): returns the
     *      embedded UTF-8 unique_id string.
     *
     * @param companyId  16-bit company identifier (host byte order).
     * @param payload    Manufacturer data bytes following the company ID.
     * @return Beacon identifier string, or empty string if not recognised.
     */
    static std::string parseBeaconId(uint16_t companyId,
                                     const std::vector<uint8_t>& payload);

    /**
     * Build a DeviceEvent from raw components, validating each field.
     *
     * @param address      MAC address string.
     * @param name         Device name (may be empty).
     * @param rssi         RSSI value.
     * @param timestamp    Unix timestamp.
     * @param beacon_id    Beacon identifier (may be empty).
     * @return DeviceEvent on success, std::nullopt if validation fails.
     */
    static std::optional<DeviceEvent> buildEvent(const std::string& address,
                                                  const std::string& name,
                                                  int rssi,
                                                  int64_t timestamp,
                                                  const std::string& beacon_id = "");

    static constexpr int MIN_RSSI = -120; ///< Minimum valid RSSI (dBm)
    static constexpr int MAX_RSSI =   10; ///< Maximum valid RSSI (dBm)
    static constexpr size_t MAX_NAME_LENGTH = 128; ///< Maximum device name length
};

} // namespace ble
