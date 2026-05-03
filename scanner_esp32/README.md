# ESP32 BLE Attendance Scanner

This folder contains the **multi-file Arduino sketch** for the ESP32 BLE scanner
that replaces (or supplements) the Linux C++ scanner for live demo setups such as
EEPEX.

---

## Project structure

```
scanner_esp32/
├── scanner_esp32.ino   Main entry point (setup / loop, LED, Wi-Fi reconnect)
├── config.h            All compile-time settings — edit this before flashing
├── logger.h            LOG_INFO / LOG_WARN / LOG_ERROR / LOG_DEBUG macros
├── ibeacon.h           iBeacon parser – public header
├── ibeacon.cpp         iBeacon parser implementation
├── dedup.h             Time-window deduplicator – public header
├── dedup.cpp           Deduplicator implementation
├── batch_sender.h      HTTP batch sender – public header
└── batch_sender.cpp    Batch sender (retry, backoff, offline buffer)
```

> **Only edit `config.h`** for normal use. All tuneable parameters are documented
> there with inline comments.

---

## How it works

1. On power-on `setup()` runs automatically — no manual command is needed:
   - Connects to Wi-Fi (restarts after 20 s timeout).
   - Syncs time from NTP so events carry valid Unix timestamps.
   - Initialises the BLE scanner in passive mode.
2. `loop()` runs continuously thereafter:
   - Runs a 1-second BLE scan burst; the BLE callback fires for every advertisement.
   - The callback parses Apple iBeacon manufacturer data, deduplicates, and enqueues accepted events.
   - `BatchSender::tick()` flushes queued events every `BATCH_INTERVAL_MS` (default 1 s)
     or immediately when `MAX_BATCH_SIZE` events accumulate.
3. Each batch is POSTed as `{"events": [...]}` to `/api/events/batch`.
4. The backend marks attendance and pushes WebSocket messages to the dashboard in real-time.

End-to-end latency from phone broadcast to dashboard update is typically **150–300 ms**.

---

## How ESP32 replaces BlueZ / D-Bus

The Linux C++ scanner and the ESP32 scanner do the same job (detect iBeacons and
forward them to the backend) but via completely different technology stacks.

### Linux C++ scanner

| Layer | Detail |
|-------|--------|
| BLE stack | **BlueZ** (kernel HCI + user-space D-Bus service) |
| Event delivery | D-Bus `InterfacesAdded` / `PropertiesChanged` signals |
| Trigger | Scanner subscribes to `org.bluez.Device1` interfaces on the adapter |
| Process model | Long-running daemon managed by `systemd` or a shell script |
| Start/stop | Must be explicitly started via `/api/scanner/start` or `sudo bash scripts/run_scanner.sh` |

### ESP32 scanner (this folder)

| Layer | Detail |
|-------|--------|
| BLE stack | **ESP-IDF / Arduino BLE stack** (built into the firmware) |
| Event delivery | **GAP scan callbacks** — `BLEAdvertisedDeviceCallbacks::onResult()` fires directly for each received advertisement packet, with no IPC overhead |
| Trigger | `BLEScan::start()` called from `loop()` — runs continuously from boot |
| Process model | Firmware runs immediately on power-on (`setup()` then `loop()`); **no systemd, no daemon, no manual start needed** |
| Start/stop | Unplug / replug the board |

**Key difference**: on Linux the BLE subsystem is a separate kernel service
(BlueZ) that communicates via D-Bus (an IPC mechanism). On ESP32 the radio
driver is part of the firmware itself and delivers advertisement packets
directly to the application via a C++ virtual-method callback with zero IPC
overhead. This eliminates the D-Bus round-trip latency that can add tens to
hundreds of milliseconds under load on a busy Linux system.

---

## Recommended hardware

| Board | Notes |
|-------|-------|
| **ESP32-WROOM-32** (DevKitC) | Most common, well-tested |
| **ESP32-WROVER** | Same, with extra PSRAM (not needed here) |
| **ESP32-C3** | Smaller, single-core; works fine |
| **ESP32-S3** | Higher performance; same API |

No external components are required. Connect an LED with a 220 Ω series resistor
between **GPIO 2** and GND for a visual status indicator (GPIO 2 is the built-in
LED on most DevKit boards). Set `LED_PIN -1` in `config.h` to disable.

---

## Software prerequisites

### 1. Arduino IDE (>= 2.x)

Download from <https://www.arduino.cc/en/software>.

### 2. ESP32 board package

**File → Preferences → Additional boards manager URLs**, add:

```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```

Then **Tools → Board → Boards Manager** → search **esp32** → install
**esp32 by Espressif Systems** (>= 2.x).

### 3. ArduinoJson library

**Sketch → Include Library → Manage Libraries** → search **ArduinoJson** →
install **ArduinoJson by Benoit Blanchon** (>= 6.21).

---

## Configuration

Open **`config.h`** and edit the values at the top:

```cpp
#define WIFI_SSID           "YourWiFiSSID"
#define WIFI_PASS           "YourWiFiPassword"
#define BACKEND_URL         "http://192.168.1.100:8000/api/events/batch"
#define SCANNER_ID          "esp32-main"    // identifies this unit in logs & WebSocket
#define RSSI_THRESHOLD      -85             // min RSSI to accept (dBm)
#define DEDUP_WINDOW_MS     5000            // dedup window (ms)
#define BATCH_INTERVAL_MS   1000            // flush interval (ms)
#define LED_PIN             2               // set -1 to disable
```

> **Finding your backend IP**: run `ip addr` (Linux/macOS) or `ipconfig`
> (Windows) on the laptop running the backend. Use the LAN IP (e.g. `192.168.1.x`),
> not `localhost` or `127.0.0.1`.

---

## Flashing

1. Open the `scanner_esp32/` folder as a sketch in Arduino IDE.
2. Select **Tools → Board → ESP32 Arduino → ESP32 Dev Module**.
3. Select the correct **Port** under **Tools → Port**.
4. Click **Upload** (Ctrl+U).
5. Open **Tools → Serial Monitor** at **115200 baud**.

Expected serial output after a successful boot:

```
===== ESP32 BLE Attendance Scanner =====
Scanner ID : esp32-main
Backend    : http://192.168.1.100:8000/api/events/batch
[INFO]  WIFI  Connecting to "MyNetwork" ...
..
[INFO]  WIFI  Connected - IP: 192.168.1.42
[INFO]  NTP   Time: 2026-05-02 12:00:00 UTC
[INFO]  BLE   Scanning  interval=100 ms  window=50 ms  RSSI>=-85  dedup=5 s
=========================================

[INFO]  SCAN  beacon_id=1:1001      mac=aa:bb:cc:dd:ee:ff rssi=-62  (queued=1, offline=0)
[INFO]  Sent 1 event(s) to backend (offline=0)
```

---

## Status LED blink patterns

| Pattern | Meaning |
|---------|---------|
| 3 quick blinks on startup | Firmware booted OK |
| Single 80 ms flash | iBeacon detected and queued |
| No blink | No iBeacons in range (or LED disabled) |

---

## Robustness features

| Feature | Detail |
|---------|--------|
| Wi-Fi auto-reconnect | Checked every 10 s; `WiFi.reconnect()` called if disconnected |
| Offline buffer | Up to `OFFLINE_BUFFER_MAX` (default 100) payloads buffered while Wi-Fi is down |
| Drain on reconnect | Buffered payloads sent in FIFO order when Wi-Fi comes back |
| Retry / backoff | Failed POSTs retried up to `HTTP_RETRY_COUNT` times with exponential backoff |
| Scan while offline | BLE scanning continues uninterrupted regardless of network state |

---

## Event payload formats

### Single event (`POST /api/events`)

```json
{
  "address":    "AA:BB:CC:DD:EE:FF",
  "rssi":       -62,
  "timestamp":  1712345678,
  "beacon_id":  "1:1001",
  "scanner_id": "esp32-main",
  "name":       "Alice's iPhone"
}
```

### Batch — ESP32 envelope (`POST /api/events/batch`)

```json
{
  "events": [
    {
      "address":    "AA:BB:CC:DD:EE:FF",
      "rssi":       -62,
      "timestamp":  1712345678,
      "beacon_id":  "1:1001",
      "scanner_id": "esp32-main"
    },
    {
      "address":    "BB:CC:DD:EE:FF:00",
      "rssi":       -70,
      "timestamp":  1712345679,
      "beacon_id":  "1:1002",
      "scanner_id": "esp32-main"
    }
  ]
}
```

### Batch — bare array (legacy Linux scanner format, also accepted)

```json
[
  {"address":"AA:BB:CC:DD:EE:FF","rssi":-62,"timestamp":1712345678,"beacon_id":"1:1001"},
  {"address":"BB:CC:DD:EE:FF:00","rssi":-70,"timestamp":1712345679,"beacon_id":"1:1002"}
]
```

| Field        | Type    | Notes |
|--------------|---------|-------|
| `address`    | string  | BLE MAC `XX:XX:XX:XX:XX:XX` |
| `rssi`       | integer | Signal strength in dBm |
| `timestamp`  | integer | Unix seconds from NTP (0 before first sync) |
| `beacon_id`  | string  | `"<major>:<minor>"` — canonical format used by this system |
| `scanner_id` | string  | Identifies this ESP32 unit; appears in WebSocket stream |
| `name`       | string  | Optional BLE advertising name |

---

## WebSocket messages (backend → dashboard)

After the ESP32 posts events the backend broadcasts them to all connected
dashboard clients.

### Raw scan event (`ws://<host>:8000/ws/scan`)

```json
{
  "type":       "scan",
  "address":    "AA:BB:CC:DD:EE:FF",
  "rssi":       -62,
  "beacon_id":  "1:1001",
  "timestamp":  1712345678,
  "scanner_id": "esp32-main"
}
```

### Attendance marked (`ws://<host>:8000/ws/attendance`)

```json
{
  "type":         "attendance_marked",
  "student_id":   7,
  "student_name": "Alice",
  "session_id":   3,
  "rssi":         -62,
  "matched_by":   "beacon",
  "timestamp":    1712345678
}
```

Silently discard messages with `"type": "ping"` (keepalive sent every 25 s).

---

## cURL test commands

```bash
# Single event
curl -s -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{"address":"AA:BB:CC:DD:EE:FF","rssi":-62,"timestamp":1712345678,"beacon_id":"1:1001","scanner_id":"esp32-main"}' \
  | python3 -m json.tool

# Batch (ESP32 envelope)
curl -s -X POST http://localhost:8000/api/events/batch \
  -H "Content-Type: application/json" \
  -d '{"events":[{"address":"AA:BB:CC:DD:EE:FF","rssi":-62,"timestamp":1712345678,"beacon_id":"1:1001","scanner_id":"esp32-main"}]}' \
  | python3 -m json.tool
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `[ERROR] Wi-Fi timeout` | Check SSID/password; ensure 2.4 GHz |
| `[WARN] NTP sync failed` | Verify internet access; timestamp=0 events rejected by backend |
| `HTTP error '-1'` | Wrong `BACKEND_URL` or firewall blocking port 8000 |
| No beacons detected | Raise `RSSI_THRESHOLD` (e.g. `-95`); confirm student app is broadcasting |
| Backend returns 422 | Check Serial Monitor for the `beacon_id`; ensure student is registered |
| `offline buffer full` | Wi-Fi down too long; increase `OFFLINE_BUFFER_MAX` |

---

## Co-existence with the Linux C++ scanner

The ESP32 scanner is a parallel, drop-in replacement. Both can run simultaneously
pointing at the same backend — the backend is stateless per event and attendance
marking is idempotent (first detection wins).

To stop the Linux scanner:

```bash
curl -X POST http://localhost:8000/api/scanner/stop
```
