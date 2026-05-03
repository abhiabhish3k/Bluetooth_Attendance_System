/**
 * config.h — Compile-time configuration for the ESP32 BLE Attendance Scanner.
 *
 * Edit the values in this file before flashing to the board.
 * All tuneable parameters are documented inline.
 */

#pragma once

// ============================================================================
// Wi-Fi
// ============================================================================

/** SSID of the 2.4 GHz Wi-Fi network. ESP32 does not support 5 GHz. */
#define WIFI_SSID           "YourWiFiSSID"

/** Wi-Fi password. */
#define WIFI_PASS           "YourWiFiPassword"

// ============================================================================
// Backend
// ============================================================================

/**
 * Full URL of the backend batch endpoint.
 * Use the LAN IP of the laptop/server — NOT localhost.
 * Find it with:  ip addr (Linux/macOS)  or  ipconfig (Windows)
 */
#define BACKEND_URL         "http://192.168.1.100:8000/api/events/batch"

/**
 * Optional Bearer token sent in the Authorization header.
 * Leave as "" to omit the header entirely.
 */
#define AUTH_TOKEN          ""

// ============================================================================
// Scanner identity
// ============================================================================

/**
 * A short string that identifies this ESP32 unit in the backend logs and in
 * WebSocket messages pushed to the dashboard.  Change this if you run more
 * than one scanner simultaneously.
 */
#define SCANNER_ID          "esp32-main"

// ============================================================================
// Status LED
// ============================================================================

/**
 * GPIO pin connected to an LED (through a 220 Ω resistor to GND).
 * GPIO 2 is the built-in blue LED on most ESP32-WROOM DevKit boards.
 * Set to -1 to disable LED support entirely.
 */
#define LED_PIN             2

// ============================================================================
// BLE scanning
// ============================================================================

/**
 * Minimum RSSI (dBm) for a detection to be accepted.
 * -85 is a good indoor default.  Tighten to -70 for a smaller demo table.
 */
#define RSSI_THRESHOLD      -85

/** BLE scan interval in milliseconds (time between scan windows). */
#define SCAN_INTERVAL_MS    100

/** BLE scan window in milliseconds (must be ≤ SCAN_INTERVAL_MS). */
#define SCAN_WINDOW_MS       50

// ============================================================================
// Deduplication
// ============================================================================

/**
 * How long (ms) to suppress repeat detections from the same BLE address.
 * 5 000 ms prevents spamming the backend while keeping attendance fast.
 */
#define DEDUP_WINDOW_MS     5000

// ============================================================================
// Batching
// ============================================================================

/** Flush the event batch to the backend this often (milliseconds). */
#define BATCH_INTERVAL_MS   1000

/** Flush immediately when this many events are queued (safety cap). */
#define MAX_BATCH_SIZE      20

// ============================================================================
// Offline buffering
// ============================================================================

/**
 * Maximum number of serialised batch payloads to keep in RAM while Wi-Fi is
 * down.  Each payload is up to ~2 KB; 100 payloads ≈ 200 KB.
 * Reduce if you see memory pressure on low-PSRAM boards.
 */
#define OFFLINE_BUFFER_MAX  100

// ============================================================================
// HTTP retry / backoff
// ============================================================================

/** Number of POST attempts before giving up and buffering the payload. */
#define HTTP_RETRY_COUNT    3

/** Base delay (ms) for exponential backoff between retries. */
#define HTTP_RETRY_BASE_MS  500

/** Per-request HTTP timeout (ms).  3–4 s is generous on a LAN. */
#define HTTP_TIMEOUT_MS     4000

// ============================================================================
// NTP
// ============================================================================

/** NTP server hostname. */
#define NTP_SERVER          "pool.ntp.org"

/** Seconds east of UTC for your timezone (0 = UTC). */
#define GMT_OFFSET_S        0

/** Daylight-saving time offset in seconds (0 = no DST). */
#define DST_OFFSET_S        0

// ============================================================================
// Logging
// ============================================================================

/**
 * Log verbosity level:
 *   0 = NONE   (no output)
 *   1 = ERROR  (fatal issues only)
 *   2 = WARN   (non-fatal issues)
 *   3 = INFO   (normal operation — recommended)
 *   4 = DEBUG  (verbose, for development)
 */
#define LOG_LEVEL           3
