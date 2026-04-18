# BLE Attendance – Student Beacon App

A Flutter application that runs on students' phones and broadcasts a BLE
beacon containing their unique student ID.  The C++ scanner on the
Raspberry Pi picks up the beacon and the Python backend marks attendance
automatically.

---

## How it works

```
Student's Phone
  └── BLE Beacon (iBeacon)
        UUID  : A8B3F9E2-C4D5-4F6A-7B8C-9D0E1F2A3B4C  (institution-wide)
        Major : 1                                         (class/institution)
        Minor : <student beacon ID>                       (assigned by admin)

Raspberry Pi (C++ Scanner)
  └── Detects beacon → emits JSON:
        {"address":"AA:BB:...","rssi":-65,"timestamp":...,"beacon_id":"1:1001"}

Python Backend
  └── Receives event → looks up student by unique_id="1:1001" → marks present
```

---

## Prerequisites

- Flutter 3.x SDK  →  https://flutter.dev/docs/get-started/install
- Android Studio or Xcode (for device-specific builds)
- Android 8.0+ or iOS 13+

---

## Setup & Build

### 1. Install Flutter dependencies

```bash
cd beacon_app
flutter pub get
```

### 2. Connect a device and run

```bash
# Android
flutter run -d <device-id>

# iOS (requires Mac + Xcode)
flutter run -d <ios-device-id>
```

### 3. Build release APK (Android)

```bash
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk
```

### 4. Build for iOS (requires Mac)

```bash
flutter build ios --release
```

---

## Student Usage

1. **Admin assigns** a numeric Beacon ID (0–65535) to each student.
2. Student installs the app, opens it, and enters:
   - Their name
   - The **Beacon ID** given by the admin
3. Tap **"Start Broadcasting"**.
4. The app begins broadcasting an iBeacon in the background.
5. Leave the app running (foreground notification on Android keeps it alive).

---

## Admin Registration

After assigning a beacon ID, register the mapping in the backend:

```bash
# Register beacon ID "1:1001" for student with database ID 5
curl -X POST http://localhost:8000/api/students/5/beacon/register \
  -H "Content-Type: application/json" \
  -d '{"beacon_id": "1:1001"}'

# Verify registration
curl http://localhost:8000/api/students/5/beacon
```

---

## Beacon Format

| Field     | Value                                    |
|-----------|------------------------------------------|
| Type      | iBeacon (Apple-compatible)               |
| Company   | 0x004C                                   |
| UUID      | `A8B3F9E2-C4D5-4F6A-7B8C-9D0E1F2A3B4C` |
| Major     | `1` (configurable, identifies class)     |
| Minor     | Student Beacon ID (0–65535)              |
| TX Power  | -59 dBm                                  |

The `beacon_id` sent to the backend is the string `"<major>:<minor>"`,
e.g. `"1:1001"` for major=1, minor=1001.

---

## Advanced Configuration

Tap **"Advanced Settings"** on the login screen to customise:
- **UUID** – change if your institution uses a different UUID
- **Major** – change to identify different classes/buildings

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Beacon not detected | Ensure Bluetooth is on and the app is in foreground |
| "Failed to start" | Grant Bluetooth/Location permissions in phone settings |
| iOS background stops | Go to Settings → Privacy → Bluetooth → enable for this app |
| Android battery optimisation | Disable battery optimisation for the app |

---

## Permissions

**Android:**
- `BLUETOOTH_ADVERTISE` – required for BLE advertising (Android 12+)
- `FOREGROUND_SERVICE` – keeps beacon alive in background

**iOS:**
- `NSBluetoothAlwaysUsageDescription` – required by App Store
- Background mode `bluetooth-peripheral` – enables background beacon

---

## License

MIT – see the root `LICENSE` file.
