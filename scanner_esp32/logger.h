/**
 * logger.h — Simple level-filtered serial logging macros.
 *
 * Usage:
 *   LOG_INFO("Wi-Fi connected to %s", ssid);
 *   LOG_WARN("RSSI too low: %d", rssi);
 *   LOG_ERROR("NTP failed after %d retries", retries);
 *   LOG_DEBUG("raw mfg bytes: len=%zu", raw.size());
 *
 * Verbosity is controlled by LOG_LEVEL in config.h.
 * Macros expand to nothing when the level is disabled, so there is zero
 * runtime overhead for suppressed messages.
 */

#pragma once

#include <Arduino.h>
#include "config.h"

// --- ERROR (level 1) --------------------------------------------------------
#if LOG_LEVEL >= 1
#  define LOG_ERROR(fmt, ...) \
     Serial.printf("[ERROR] " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG_ERROR(fmt, ...) do {} while (0)
#endif

// --- WARN (level 2) ---------------------------------------------------------
#if LOG_LEVEL >= 2
#  define LOG_WARN(fmt, ...) \
     Serial.printf("[WARN]  " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG_WARN(fmt, ...) do {} while (0)
#endif

// --- INFO (level 3) ---------------------------------------------------------
#if LOG_LEVEL >= 3
#  define LOG_INFO(fmt, ...) \
     Serial.printf("[INFO]  " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG_INFO(fmt, ...) do {} while (0)
#endif

// --- DEBUG (level 4) --------------------------------------------------------
#if LOG_LEVEL >= 4
#  define LOG_DEBUG(fmt, ...) \
     Serial.printf("[DEBUG] " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG_DEBUG(fmt, ...) do {} while (0)
#endif
