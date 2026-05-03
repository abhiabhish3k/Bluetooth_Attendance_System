/**
 * ibeacon.h — Apple iBeacon advertisement parser.
 *
 * Extracts the Major and Minor values from the BLE manufacturer data of an
 * Apple iBeacon advertisement and returns them as the canonical beacon_id
 * string "<major>:<minor>" used throughout this system.
 *
 * Returns an empty string for any non-iBeacon advertisement.
 */

#pragma once

#include <Arduino.h>
#include <BLEAdvertisedDevice.h>

/**
 * Parse an iBeacon advertisement.
 *
 * @param device  A BLEAdvertisedDevice received in the scan callback.
 * @return        "<major>:<minor>" string, or "" if not an iBeacon.
 */
String parseIBeacon(BLEAdvertisedDevice& device);
