import 'dart:convert';
import 'package:beacon_broadcast/beacon_broadcast.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/student_config.dart';

/// Manages BLE beacon broadcasting via the beacon_broadcast package.
///
/// The beacon is an iBeacon-compatible advertisement with:
///   UUID  : BeaconDefaults.uuid  (institution-wide, matches scanner config)
///   Major : BeaconDefaults.major (class/institution identifier)
///   Minor : student's beaconMinor (numeric unique identifier, 0–65535)
///
/// A foreground service notification keeps the broadcast alive when the
/// app is in the background on Android.
class BeaconService {
  static const String _prefKey = 'student_config';

  final BeaconBroadcast _beacon = BeaconBroadcast();

  bool _broadcasting = false;
  StudentConfig? _config;

  bool get isBroadcasting => _broadcasting;
  StudentConfig? get config => _config;

  // -------------------------------------------------------------------------
  // Persistence helpers
  // -------------------------------------------------------------------------

  Future<void> loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefKey);
    if (raw != null) {
      _config = StudentConfig.fromMap(
          Map<String, dynamic>.from(jsonDecode(raw) as Map));
    }
  }

  Future<void> saveConfig(StudentConfig cfg) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefKey, jsonEncode(cfg.toMap()));
    _config = cfg;
  }

  Future<void> clearConfig() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_prefKey);
    _config = null;
  }

  // -------------------------------------------------------------------------
  // Foreground service initialisation (Android)
  // -------------------------------------------------------------------------

  Future<void> initForegroundTask() async {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'ble_attendance_beacon',
        channelName: 'BLE Attendance Beacon',
        channelDescription: 'Broadcasting your student ID via BLE',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: true,
        playSound: false,
      ),
      foregroundTaskOptions: const ForegroundTaskOptions(
        interval: 5000,
        isOnceEvent: false,
        autoRunOnBoot: true,
        allowWakeLock: true,
        allowWifiLock: false,
      ),
    );
  }

  // -------------------------------------------------------------------------
  // Start / Stop broadcasting
  // -------------------------------------------------------------------------

  Future<bool> startBroadcasting(StudentConfig cfg) async {
    if (_broadcasting) await stopBroadcasting();

    await saveConfig(cfg);

    _beacon
        .setUUID(cfg.beaconUuid)
        .setMajorId(cfg.beaconMajor)
        .setMinorId(cfg.beaconMinor)
        .setTransmissionPower(cfg.txPower)
        .setAdvertiseMode(AdvertiseMode.lowLatency);

    await _beacon.start();

    // Check if it started successfully
    final transmitting = await _beacon.isAdvertising();
    _broadcasting = transmitting ?? false;
    return _broadcasting;
  }

  Future<void> stopBroadcasting() async {
    await _beacon.stop();
    _broadcasting = false;
  }

  Future<bool> isAdvertising() async {
    final result = await _beacon.isAdvertising();
    _broadcasting = result ?? false;
    return _broadcasting;
  }

  /// Re-start the beacon after boot (call from foreground task handler).
  Future<void> restoreFromPrefs() async {
    await loadConfig();
    if (_config != null) {
      await startBroadcasting(_config!);
    }
  }
}
