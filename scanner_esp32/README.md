# ESP32 BLE Attendance Scanner

This folder contains the Arduino sketch for the **ESP32 BLE scanner** that
replaces (or supplements) the Linux C++ scanner for live demo setups such as
EEPEX.

---

## How it works

1. The ESP32 connects to your Wi-Fi network and syncs time via NTP.
2. It performs **continuous passive BLE scanning** and fires a callback for
   every received advertisement.
3. The callback:
   - Parses the **Apple iBeacon** manufacturer data.
   - Extracts **Major** and **Minor** values and formats them as
     `"<major>:<minor>"` — the canonical `beacon_id` used by the backend.
   - Applies **local deduplication** (default 5 s window) to avoid spamming
     the backend with repeated detections of the same device.
4. Events are queued in an in-memory batch and **flushed every 1 second**
   (or immediately when the batch reaches 20 events).
5. The batch is sent as a single **HTTP POST** to the backend's
   `/api/events/batch` endpoint in the `{"events": [...]}` envelope format.

End-to-end latency from phone broadcast to dashboard update is typically
**150–300 ms** over a local Wi-Fi network.

---

## Recommended hardware

| Board | Notes |
|-------|-------|
| **ESP32-WROOM-32** (DevKitC) | Most common, well-tested |
| **ESP32-WROVER** | Same, with extra 8 MB PSRAM (not needed here) |
| **ESP32-C3** | Smaller, single-core; works fine |
| **ESP32-S3** | Higher performance; same API |

**No external components required** — just a USB cable, a 5 V micro-USB
power supply or laptop, and a Wi-Fi access point.

---

## Wiring

The sketch uses only the onboard BLE and Wi-Fi radios.  No additional wiring
is required.

If you want to add a status LED:

| ESP32 Pin | Component |
|-----------|-----------|
| GPIO 2    | LED anode (through 220 Ω resistor) → GND |

> The LED is not implemented in the sketch; add a `digitalWrite` call in
> `setup()` / `sendBatch()` as desired.

---

## Software prerequisites

### 1. Arduino IDE (≥ 2.x) or PlatformIO

Download from <https://www.arduino.cc/en/software>.

### 2. ESP32 board package

In Arduino IDE: **File → Preferences → Additional boards manager URLs**, add:

```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```

Then: **Tools → Board → Boards Manager** → search **esp32** → install
**esp32 by Espressif Systems** (≥ 2.x).

### 3. ArduinoJson library

**Sketch → Include Library → Manage Libraries** → search **ArduinoJson** →
install **ArduinoJson by Benoit Blanchon** (≥ 6.21).

---

## Configuration

Open `scanner_esp32.ino` and edit the `CONFIGURATION` section at the top:

```cpp
#define WIFI_SSID       "YourWiFiSSID"        // ← Wi-Fi network name
#define WIFI_PASS       "YourWiFiPassword"    // ← Wi-Fi password
#define BACKEND_URL     "http://192.168.1.100:8000/api/events/batch"
                                               // ← laptop/server IP:port
#define AUTH_TOKEN      ""                     // ← optional bearer token
#define RSSI_THRESHOLD  -85                    // ← min RSSI to accept (dBm)
#define DEDUP_WINDOW_MS 5000                   // ← dedup window (ms)
#define BATCH_INTERVAL_MS 1000                 // ← flush interval (ms)
```

> **Finding your backend IP**: run `ip addr` (Linux/macOS) or `ipconfig`
> (Windows) on the laptop running the backend.  Use the LAN IP (e.g.
> `192.168.1.x`), not `localhost` or `127.0.0.1`.

---

## Flashing

1. Select **Tools → Board → ESP32 Arduino → ESP32 Dev Module** (or your board).
2. Select the correct **Port** under **Tools → Port**.
3. Click **Upload** (Ctrl+U).
4. Open **Tools → Serial Monitor** at **115200 baud** to watch scan output.

Expected serial output after a successful boot:

```
===== ESP32 BLE Attendance Scanner =====
[WIFI] Connecting to "MyNetwork" …
..
[WIFI] Connected – IP: 192.168.1.42
[NTP]  Syncing …
[NTP]  Time: 2026-05-02 12:00:00 UTC
[BLE]  Scanning (interval=100 ms, window=50 ms, RSSI≥-85, dedup=5 s)
[HTTP] Backend: http://192.168.1.100:8000/api/events/batch
==========================================

[SCAN] beacon_id=1:1001      mac=aa:bb:cc:dd:ee:ff rssi=-62 (queued=1)
[INFO] Sent 1 event(s) → HTTP 200
```

---

## Event payload

Each batch POST contains a JSON body:

```json
{
  "events": [
    {
      "address":   "AA:BB:CC:DD:EE:FF",
      "rssi":      -62,
      "timestamp": 1712345678,
      "beacon_id": "1:1001",
      "name":      "Alice's iPhone"
    }
  ]
}
```

| Field       | Type    | Notes |
|-------------|---------|-------|
| `address`   | string  | MAC address `XX:XX:XX:XX:XX:XX` |
| `rssi`      | integer | Signal strength in dBm |
| `timestamp` | integer | **Unix seconds** (from NTP) |
| `beacon_id` | string  | `"<major>:<minor>"` — same format as Linux scanner |
| `name`      | string  | Optional device advertising name |

---

## cURL test commands

### Single event  (`POST /api/events`)

```bash
curl -s -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "address":   "AA:BB:CC:DD:EE:FF",
    "rssi":      -62,
    "timestamp": 1712345678,
    "beacon_id": "1:1001",
    "name":      "Test Phone"
  }' | python3 -m json.tool
```

### Batch (ESP32 envelope — `POST /api/events/batch`)

```bash
curl -s -X POST http://localhost:8000/api/events/batch \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {
        "address":   "AA:BB:CC:DD:EE:FF",
        "rssi":      -62,
        "timestamp": 1712345678,
        "beacon_id": "1:1001"
      },
      {
        "address":   "BB:CC:DD:EE:FF:00",
        "rssi":      -70,
        "timestamp": 1712345679,
        "beacon_id": "1:1002"
      }
    ]
  }' | python3 -m json.tool
```

### Batch (bare array — legacy Linux scanner format)

```bash
curl -s -X POST http://localhost:8000/api/events/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"address":"AA:BB:CC:DD:EE:FF","rssi":-62,"timestamp":1712345678,"beacon_id":"1:1001"},
    {"address":"BB:CC:DD:EE:FF:00","rssi":-70,"timestamp":1712345679,"beacon_id":"1:1002"}
  ]' | python3 -m json.tool
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `[ERROR] Wi-Fi timeout` | Check SSID/password; ensure 2.4 GHz band |
| `[WARN] NTP sync failed` | Verify internet access; events with timestamp 0 will be rejected by backend |
| `HTTP POST failed (-1)` | Wrong BACKEND_URL or laptop firewall blocking port 8000 |
| No beacons detected | Increase `RSSI_THRESHOLD` (e.g. −95); confirm student app is broadcasting |
| Backend returns 422 | Check Serial Monitor for the raw beacon_id; ensure student is registered |

---

## Co-existence with the Linux C++ scanner

The ESP32 scanner is a **parallel, drop-in replacement**.  Both can run
simultaneously pointing at the same backend — the backend is stateless per
event and the attendance marking is idempotent (first detection wins).

To stop the Linux scanner while using the ESP32:

```bash
curl -X POST http://localhost:8000/api/scanner/stop
```
