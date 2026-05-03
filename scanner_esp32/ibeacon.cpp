/**
 * ibeacon.cpp — Apple iBeacon advertisement parser implementation.
 *
 * Apple iBeacon manufacturer data layout (from BLEAdvertisedDevice::getManufacturerData()):
 *
 *   Byte  0    0x4C  – Apple company ID (low byte, little-endian 0x004C)
 *   Byte  1    0x00  – Apple company ID (high byte)
 *   Byte  2    0x02  – iBeacon frame subtype
 *   Byte  3    0x15  – Subtype length = 21
 *   Bytes 4-19       – Proximity UUID (16 bytes)
 *   Bytes 20-21      – Major (big-endian uint16)
 *   Bytes 22-23      – Minor (big-endian uint16)
 *   Byte  24         – TX Power (calibrated RSSI at 1 m)
 *
 * Total minimum length: 25 bytes.
 */

#include "ibeacon.h"

static const uint8_t APPLE_CO_LO        = 0x4C;
static const uint8_t APPLE_CO_HI        = 0x00;
static const uint8_t IBEACON_SUBTYPE    = 0x02;
static const uint8_t IBEACON_SUBTYPE_LEN = 0x15;  // 21
static const size_t  IBEACON_MIN_BYTES  = 25;

String parseIBeacon(BLEAdvertisedDevice& device) {
    if (!device.haveManufacturerData()) return "";

    std::string raw = device.getManufacturerData();
    if (raw.size() < IBEACON_MIN_BYTES) return "";

    // Bytes 0-1: Apple company ID (little-endian 0x004C)
    if ((uint8_t)raw[0] != APPLE_CO_LO || (uint8_t)raw[1] != APPLE_CO_HI) return "";

    // Byte 2: iBeacon subtype; Byte 3: subtype length (must be 0x15 = 21)
    if ((uint8_t)raw[2] != IBEACON_SUBTYPE)      return "";
    if ((uint8_t)raw[3] != IBEACON_SUBTYPE_LEN)  return "";

    // Major: bytes 20-21 (big-endian); Minor: bytes 22-23 (big-endian)
    uint16_t major = ((uint8_t)raw[20] << 8) | (uint8_t)raw[21];
    uint16_t minor = ((uint8_t)raw[22] << 8) | (uint8_t)raw[23];

    return String(major) + ":" + String(minor);
}
