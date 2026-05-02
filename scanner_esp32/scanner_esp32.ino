/**
 * scanner_esp32.ino
 * ESP32 BLE iBeacon Scanner for the BLE Attendance System
 *
 * Continuously scans for BLE iBeacon advertisements, extracts the
 * beacon_id as "<major>:<minor>", deduplicates locally, and batch-sends
 * events to the Python FastAPI backend over Wi-Fi via HTTP POST.
 *
 * Timestamp unit: Unix seconds (from NTP).  The backend accepts both
 * Unix-second and Unix-millisecond values but seconds are the canonical form.
 *
 * Required Arduino libraries (install via Library Manager):
 *   - ArduinoJson  >= 6.21  (search "ArduinoJson" by Benoit Blanchon)
 *
 * Built-in ESP32 libraries used (no extra install needed):
 *   - ESP32 BLE Arduino  (included in esp32 board package)
 *   - WiFi
 *   - HTTPClient
 *
 * Board: Any ESP32 dev-board (WROOM-32, WROVER, C3, S3, etc.)
 * See scanner_esp32/README.md for full wiring and flashing instructions.
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <map>
#include <string>

// ============================================================================
// ▸ CONFIGURATION — edit before flashing
// ============================================================================

// Wi-Fi credentials
#define WIFI_SSID    "YourWiFiSSID"
#define WIFI_PASS    "YourWiFiPassword"

// Backend batch endpoint URL
// Use /api/events/batch for batch sending (recommended)
#define BACKEND_URL  "http://192.168.1.100:8000/api/events/batch"

// Optional Bearer token for Authorization header; leave "" to disable
#define AUTH_TOKEN   ""

// Minimum RSSI (dBm) to accept a detection.
// −85 is a practical indoor cut-off; tighten to −70 for a smaller demo area.
#define RSSI_THRESHOLD   -85

// Local deduplication window: ignore repeat detections from the same device
// within this many milliseconds.  5 000 ms = 5 s is a good default.
#define DEDUP_WINDOW_MS  5000

// How often (ms) to flush the event batch to the backend.
// 1 000 ms gives near-real-time updates without flooding the network.
#define BATCH_INTERVAL_MS  1000

// Flush immediately when this many events are queued (safety valve).
#define MAX_BATCH_SIZE  20

// BLE scan parameters (lower interval+window = more responsive; more power)
#define SCAN_INTERVAL_MS  100   // ms between scan windows
#define SCAN_WINDOW_MS     50   // ms per scan window (must be ≤ SCAN_INTERVAL_MS)

// NTP settings
#define NTP_SERVER    "pool.ntp.org"
#define GMT_OFFSET_S  0   // adjust for local timezone if desired
#define DST_OFFSET_S  0

// ============================================================================
// Apple iBeacon frame constants
// Manufacturer data layout (bytes within getManufacturerData()):
//   [0]    0x4C  (Apple company ID, low byte)
//   [1]    0x00  (Apple company ID, high byte)
//   [2]    0x02  (iBeacon subtype)
//   [3]    0x15  (subtype length = 21)
//   [4–19] UUID  (16 bytes)
//   [20–21] Major (big-endian)
//   [22–23] Minor (big-endian)
//   [24]   TX Power
// ============================================================================
static const uint8_t APPLE_CO_LO        = 0x4C;
static const uint8_t APPLE_CO_HI        = 0x00;
static const uint8_t IBEACON_SUBTYPE    = 0x02;
static const uint8_t IBEACON_SUBTYPE_LEN = 0x15;
static const size_t  IBEACON_MIN_BYTES  = 25;

// ============================================================================
// Globals
// ============================================================================
BLEScan* bleScan = nullptr;

// Deduplication map: MAC string → last-accepted millis()
std::map<std::string, unsigned long> lastSeenMs;

// JSON batch buffer.  8 192 bytes fits ~80 events @ ~100 bytes each.
DynamicJsonDocument batchDoc(8192);
JsonArray batchArray;
int       batchCount      = 0;
unsigned long lastBatchMs = 0;

// ============================================================================
// parseIBeacon
// Returns "major:minor" string if device is an iBeacon, empty string otherwise.
// ============================================================================
String parseIBeacon(BLEAdvertisedDevice& device) {
    if (!device.haveManufacturerData()) return "";

    std::string raw = device.getManufacturerData();
    if (raw.size() < IBEACON_MIN_BYTES) return "";

    // Bytes 0–1: Apple company ID (little-endian 0x004C)
    if ((uint8_t)raw[0] != APPLE_CO_LO || (uint8_t)raw[1] != APPLE_CO_HI) return "";

    // Byte 2: iBeacon subtype; byte 3: subtype length (must be 0x15 = 21)
    if ((uint8_t)raw[2] != IBEACON_SUBTYPE)     return "";
    if ((uint8_t)raw[3] != IBEACON_SUBTYPE_LEN) return "";

    // Major: bytes 20–21 (big-endian); Minor: bytes 22–23 (big-endian)
    uint16_t major = ((uint8_t)raw[20] << 8) | (uint8_t)raw[21];
    uint16_t minor = ((uint8_t)raw[22] << 8) | (uint8_t)raw[23];

    return String(major) + ":" + String(minor);
}

// ============================================================================
// getUnixSeconds
// Returns current UTC time as Unix seconds (requires NTP sync).
// Falls back to 0 if time is not yet synced, so events will be rejected by
// the backend – the device will retry in the next batch cycle.
// ============================================================================
int64_t getUnixSeconds() {
    time_t now;
    time(&now);
    return (int64_t)now;
}

// ============================================================================
// resetBatch – clear the JSON document and start a fresh array
// ============================================================================
void resetBatch() {
    batchDoc.clear();
    batchArray = batchDoc.to<JsonArray>();
    batchCount = 0;
    lastBatchMs = millis();
}

// ============================================================================
// sendBatch – serialise current batch and POST to backend
// ============================================================================
void sendBatch() {
    if (batchCount == 0) {
        lastBatchMs = millis();
        return;
    }

    // Wrap as {"events": [...]} — the backend accepts this ESP32 envelope format
    // as well as the bare array format used by the Linux C++ scanner.
    DynamicJsonDocument envelope(8192 + 64);
    envelope["events"] = batchArray;

    String payload;
    serializeJson(envelope, payload);

    if (WiFi.status() != WL_CONNECTED) {
        Serial.printf("[WARN] Wi-Fi down – dropping batch of %d event(s)\n", batchCount);
        resetBatch();
        return;
    }

    HTTPClient http;
    http.begin(BACKEND_URL);
    http.addHeader("Content-Type", "application/json");
    if (strlen(AUTH_TOKEN) > 0) {
        http.addHeader("Authorization", String("Bearer ") + AUTH_TOKEN);
    }
    http.setTimeout(3000);  // 3 s is generous for a LAN demo

    int code = http.POST(payload);
    if (code > 0) {
        Serial.printf("[INFO] Sent %d event(s) → HTTP %d\n", batchCount, code);
    } else {
        Serial.printf("[WARN] HTTP POST failed (%s) – events dropped\n",
                      http.errorToString(code).c_str());
    }
    http.end();

    resetBatch();
}

// ============================================================================
// BLE scan callback
// ============================================================================
class ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice device) override {
        int rssi = device.getRSSI();
        if (rssi < RSSI_THRESHOLD) return;

        // Only process iBeacons (our student app advertises iBeacons)
        String beaconId = parseIBeacon(device);
        if (beaconId.isEmpty()) return;

        std::string mac = device.getAddress().toString();
        unsigned long now = millis();

        // Local deduplication
        auto it = lastSeenMs.find(mac);
        if (it != lastSeenMs.end() && (now - it->second) < (unsigned long)DEDUP_WINDOW_MS) {
            return;  // too soon – skip duplicate
        }
        lastSeenMs[mac] = now;

        // Append to batch
        JsonObject ev = batchArray.createNestedObject();
        ev["address"]   = mac.c_str();
        ev["rssi"]      = rssi;
        ev["timestamp"] = (long long)getUnixSeconds();  // Unix seconds (NTP)
        ev["beacon_id"] = beaconId.c_str();
        if (device.haveName()) {
            std::string name = device.getName();
            if (!name.empty()) ev["name"] = name.c_str();
        }
        batchCount++;

        Serial.printf("[SCAN] beacon_id=%-10s mac=%s rssi=%d (queued=%d)\n",
                      beaconId.c_str(), mac.c_str(), rssi, batchCount);

        // Flush immediately if batch is full
        if (batchCount >= MAX_BATCH_SIZE) {
            sendBatch();
        }
    }
};

// ============================================================================
// setup
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n===== ESP32 BLE Attendance Scanner =====");

    // ── Wi-Fi ──────────────────────────────────────────────────────────────
    Serial.printf("[WIFI] Connecting to \"%s\" …\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    unsigned long wifiStart = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - wifiStart > 20000) {
            Serial.println("\n[ERROR] Wi-Fi timeout – restarting in 5 s …");
            delay(5000);
            ESP.restart();
        }
    }
    Serial.printf("\n[WIFI] Connected – IP: %s\n", WiFi.localIP().toString().c_str());

    // ── NTP time sync ──────────────────────────────────────────────────────
    Serial.print("[NTP]  Syncing …");
    configTime(GMT_OFFSET_S, DST_OFFSET_S, NTP_SERVER);
    struct tm ti;
    bool ntpOk = false;
    for (int i = 0; i < 20; i++) {
        if (getLocalTime(&ti)) { ntpOk = true; break; }
        delay(500);
        Serial.print(".");
    }
    if (ntpOk) {
        Serial.printf("\n[NTP]  Time: %04d-%02d-%02d %02d:%02d:%02d UTC\n",
                      ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
                      ti.tm_hour, ti.tm_min, ti.tm_sec);
    } else {
        Serial.println("\n[WARN] NTP sync failed – timestamps will be invalid until sync succeeds");
    }

    // ── Batch buffer ───────────────────────────────────────────────────────
    resetBatch();

    // ── BLE ────────────────────────────────────────────────────────────────
    BLEDevice::init("");
    bleScan = BLEDevice::getScan();
    // wantDuplicates=true: receive each advertisement independently so our
    // time-based dedup window controls re-detection, not the BLE stack.
    bleScan->setAdvertisedDeviceCallbacks(new ScanCallbacks(), /*wantDuplicates=*/true);
    bleScan->setActiveScan(false);  // passive scan – faster, lower power
    bleScan->setInterval(SCAN_INTERVAL_MS);
    bleScan->setWindow(SCAN_WINDOW_MS);

    Serial.printf("[BLE]  Scanning (interval=%d ms, window=%d ms, RSSI≥%d, dedup=%d s)\n",
                  SCAN_INTERVAL_MS, SCAN_WINDOW_MS, RSSI_THRESHOLD, DEDUP_WINDOW_MS / 1000);
    Serial.printf("[HTTP] Backend: %s\n", BACKEND_URL);
    Serial.println("==========================================\n");
}

// ============================================================================
// loop
// ============================================================================
void loop() {
    // Run a 1-second BLE scan burst (non-blocking; callback fires inline)
    bleScan->start(1, /*is_continue=*/false);

    // Flush accumulated events when the batch interval has elapsed
    if (millis() - lastBatchMs >= (unsigned long)BATCH_INTERVAL_MS) {
        sendBatch();
    }

    // Periodically evict stale dedup entries to prevent unbounded map growth
    // (~500 entries before pruning is safe; a 50-student demo never reaches this)
    if (lastSeenMs.size() > 500) {
        unsigned long now = millis();
        for (auto it = lastSeenMs.begin(); it != lastSeenMs.end(); ) {
            if (now - it->second > (unsigned long)DEDUP_WINDOW_MS * 4) {
                it = lastSeenMs.erase(it);
            } else {
                ++it;
            }
        }
    }
}
