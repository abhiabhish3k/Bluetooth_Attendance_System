/**
 * scanner_esp32.ino — ESP32 BLE Attendance Scanner (main entry point)
 *
 * The sketch is split into multiple files for clarity:
 *
 *   config.h         All compile-time settings (Wi-Fi, backend URL, RSSI, …)
 *   logger.h         LOG_INFO / LOG_WARN / LOG_ERROR / LOG_DEBUG macros
 *   ibeacon.h/.cpp   Apple iBeacon manufacturer-data parser → beacon_id
 *   dedup.h/.cpp     Time-window BLE deduplicator
 *   batch_sender.h/.cpp  HTTP batch POST with retry/backoff & offline buffer
 *
 * Edit config.h before flashing – do NOT change any other file for normal use.
 *
 * Required Arduino libraries (install via Library Manager):
 *   - ArduinoJson >= 6.21  (search "ArduinoJson" by Benoit Blanchon)
 *
 * Built-in ESP32 libraries (no extra install needed):
 *   - ESP32 BLE Arduino  (included in the esp32 board package)
 *   - WiFi, HTTPClient
 *
 * Board: Any ESP32 dev-board (WROOM-32, WROVER, C3, S3, …)
 * See scanner_esp32/README.md for full flashing and operation instructions.
 */

#include "config.h"
#include "logger.h"
#include "ibeacon.h"
#include "dedup.h"
#include "batch_sender.h"

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <WiFi.h>
#include <time.h>

// ============================================================================
// Globals
// ============================================================================

BLEScan*     bleScan = nullptr;
Deduplicator dedup;

// ── LED helpers ──────────────────────────────────────────────────────────────
// Non-blocking LED: set a future "off" time with ledFlash(), call ledTick()
// from loop() to extinguish the LED without using delay().
#if LED_PIN >= 0
static unsigned long _ledOffAt = 0;

static void ledFlash(unsigned long durationMs) {
    digitalWrite(LED_PIN, HIGH);
    _ledOffAt = millis() + durationMs;
}

static void ledTick() {
    if (_ledOffAt > 0 && millis() >= _ledOffAt) {
        digitalWrite(LED_PIN, LOW);
        _ledOffAt = 0;
    }
}
#else
static inline void ledFlash(unsigned long) {}
static inline void ledTick() {}
#endif

// ============================================================================
// BLE scan callback
// ============================================================================

class ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice device) override {
        int rssi = device.getRSSI();
        if (rssi < RSSI_THRESHOLD) return;

        // Only process Apple iBeacon advertisements
        String beaconId = parseIBeacon(device);
        if (beaconId.isEmpty()) return;

        std::string mac = device.getAddress().toString();

        // Deduplicate within the configured time window
        if (!dedup.accept(mac)) return;

        // Timestamp: Unix seconds from NTP (0 before first sync)
        time_t now;
        time(&now);
        int64_t ts = (int64_t)now;

        String name = "";
        if (device.haveName()) {
            name = String(device.getName().c_str());
        }

        batchSender.enqueue(String(mac.c_str()), rssi, beaconId, ts, name);

        // Brief LED flash to indicate a detected beacon
        ledFlash(80);

        LOG_INFO("SCAN  beacon_id=%-10s mac=%s rssi=%d  (queued=%d, offline=%d)",
                 beaconId.c_str(), mac.c_str(), rssi,
                 batchSender.queuedCount(), batchSender.bufferedCount());
    }
};

// ============================================================================
// Wi-Fi helpers
// ============================================================================

static void connectWiFi() {
    LOG_INFO("WIFI  Connecting to \"%s\" ...", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - start > 20000) {
            Serial.println();
            LOG_ERROR("Wi-Fi timeout – restarting in 5 s ...");
            delay(5000);
            ESP.restart();
        }
    }
    Serial.println();
    LOG_INFO("WIFI  Connected – IP: %s", WiFi.localIP().toString().c_str());
}

// ============================================================================
// setup – runs once on power-on / reset
// ============================================================================

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n===== ESP32 BLE Attendance Scanner =====");
    Serial.printf("Scanner ID : %s\n", SCANNER_ID);
    Serial.printf("Backend    : %s\n", BACKEND_URL);

#if LED_PIN >= 0
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    // Three quick blinks on startup to confirm LED is working
    for (int i = 0; i < 3; i++) {
        digitalWrite(LED_PIN, HIGH); delay(100);
        digitalWrite(LED_PIN, LOW);  delay(150);
    }
#endif

    // ── Wi-Fi ──────────────────────────────────────────────────────────────
    connectWiFi();

    // ── NTP time sync ──────────────────────────────────────────────────────
    Serial.print("[INFO]  NTP   Syncing ...");
    configTime(GMT_OFFSET_S, DST_OFFSET_S, NTP_SERVER);
    struct tm ti;
    bool ntpOk = false;
    for (int i = 0; i < 20; i++) {
        if (getLocalTime(&ti)) { ntpOk = true; break; }
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    if (ntpOk) {
        LOG_INFO("NTP   Time: %04d-%02d-%02d %02d:%02d:%02d UTC",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
                 ti.tm_hour, ti.tm_min, ti.tm_sec);
    } else {
        LOG_WARN("NTP   Sync failed – timestamps will be 0 until NTP succeeds");
    }

    // ── BLE ────────────────────────────────────────────────────────────────
    BLEDevice::init("");
    bleScan = BLEDevice::getScan();
    // wantDuplicates=true: every advertisement fires the callback so our
    // time-window deduplicator (not the BLE stack) controls re-detection.
    bleScan->setAdvertisedDeviceCallbacks(new ScanCallbacks(),
                                          /*wantDuplicates=*/true);
    bleScan->setActiveScan(false);   // passive scan – faster, lower power
    bleScan->setInterval(SCAN_INTERVAL_MS);
    bleScan->setWindow(SCAN_WINDOW_MS);

    LOG_INFO("BLE   Scanning  interval=%d ms  window=%d ms  RSSI>=%d  dedup=%d s",
             SCAN_INTERVAL_MS, SCAN_WINDOW_MS, RSSI_THRESHOLD, DEDUP_WINDOW_MS / 1000);
    Serial.println("=========================================\n");
}

// ============================================================================
// loop – runs continuously after setup()
// ============================================================================

static unsigned long _lastWifiCheck = 0;

void loop() {
    // ── Wi-Fi auto-reconnect (check every 10 s) ───────────────────────────
    if (millis() - _lastWifiCheck > 10000) {
        _lastWifiCheck = millis();
        if (WiFi.status() != WL_CONNECTED) {
            LOG_WARN("Wi-Fi disconnected – reconnecting ...");
            WiFi.reconnect();
        }
    }

    // ── BLE scan burst (1 s; callback fires inline per advertisement) ─────
    bleScan->start(1, /*is_continue=*/false);

    // ── Flush event batch to backend ──────────────────────────────────────
    batchSender.tick();

    // ── Evict stale dedup entries ─────────────────────────────────────────
    dedup.prune();

    // ── LED tick (non-blocking LED-off) ───────────────────────────────────
    ledTick();
}
