import 'dart:async';
import 'package:flutter/material.dart';

import '../models/student_config.dart';
import '../services/beacon_service.dart';
import 'login_screen.dart';

/// Main screen shown while the beacon is active.
///
/// Displays:
///  - Broadcast status (on/off, animated indicator)
///  - Student name and beacon ID
///  - iBeacon parameters (UUID, Major, Minor)
///  - Battery-saving tip
///  - Buttons to stop broadcasting / change student
class BeaconScreen extends StatefulWidget {
  final BeaconService beaconService;
  final StudentConfig config;

  const BeaconScreen({
    super.key,
    required this.beaconService,
    required this.config,
  });

  @override
  State<BeaconScreen> createState() => _BeaconScreenState();
}

class _BeaconScreenState extends State<BeaconScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  late Animation<double> _stoppedAnimation;

  Timer? _statusTimer;
  bool _broadcasting = false;
  String _statusMessage = 'Starting…';

  @override
  void initState() {
    super.initState();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);

    _pulseAnimation =
        Tween<double>(begin: 0.85, end: 1.0).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeInOut,
    ));

    _stoppedAnimation = const AlwaysStoppedAnimation(1.0);

    _startBeacon();
    _statusTimer =
        Timer.periodic(const Duration(seconds: 5), (_) => _refreshStatus());
  }

  Future<void> _startBeacon() async {
    setState(() => _statusMessage = 'Starting beacon…');
    final ok = await widget.beaconService.startBroadcasting(widget.config);
    if (!mounted) return;
    setState(() {
      _broadcasting = ok;
      _statusMessage = ok
          ? 'Broadcasting your beacon ID'
          : 'Failed to start – check Bluetooth & permissions';
    });
  }

  Future<void> _refreshStatus() async {
    final ok = await widget.beaconService.isAdvertising();
    if (!mounted) return;
    setState(() {
      _broadcasting = ok;
      _statusMessage =
          ok ? 'Broadcasting your beacon ID' : 'Beacon stopped';
    });
  }

  Future<void> _stopAndLogout() async {
    await widget.beaconService.stopBroadcasting();
    await widget.beaconService.clearConfig();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) =>
            LoginScreen(beaconService: widget.beaconService),
      ),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _statusTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cfg = widget.config;

    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: const Text('BLE Attendance',
            style: TextStyle(color: Colors.white)),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: Color(0xFF90CAF9)),
            tooltip: 'Change student',
            onPressed: _stopAndLogout,
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: 24),

              // Animated pulse indicator
              ScaleTransition(
                scale: _broadcasting ? _pulseAnimation : _stoppedAnimation,
                child: Container(
                  width: 140,
                  height: 140,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _broadcasting
                        ? const Color(0xFF0288D1).withOpacity(0.15)
                        : Colors.grey.withOpacity(0.15),
                    border: Border.all(
                      color: _broadcasting
                          ? const Color(0xFF4FC3F7)
                          : Colors.grey,
                      width: 3,
                    ),
                  ),
                  child: Icon(
                    _broadcasting
                        ? Icons.bluetooth_searching
                        : Icons.bluetooth_disabled,
                    size: 72,
                    color: _broadcasting
                        ? const Color(0xFF4FC3F7)
                        : Colors.grey,
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Status badge
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: _broadcasting
                      ? const Color(0xFF1B5E20)
                      : const Color(0xFF4E342E),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _broadcasting ? Icons.circle : Icons.circle_outlined,
                      size: 10,
                      color: _broadcasting ? Colors.greenAccent : Colors.orange,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _broadcasting ? 'ACTIVE' : 'INACTIVE',
                      style: TextStyle(
                        color: _broadcasting
                            ? Colors.greenAccent
                            : Colors.orange,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 8),
              Text(
                _statusMessage,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF90CAF9), fontSize: 14),
              ),

              const SizedBox(height: 32),

              // Student card
              _infoCard(
                title: 'Student',
                rows: [
                  _row('Name', cfg.studentName),
                  _row('Beacon ID', cfg.beaconId),
                ],
              ),

              const SizedBox(height: 16),

              // iBeacon parameters card
              _infoCard(
                title: 'iBeacon Parameters',
                rows: [
                  _row('UUID', cfg.beaconUuid, mono: true, wrap: true),
                  _row('Major', cfg.beaconMajor.toString()),
                  _row('Minor', cfg.beaconMinor.toString()),
                  _row('TX Power', '${cfg.txPower} dBm'),
                ],
              ),

              const SizedBox(height: 16),

              // Battery tip
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A237E).withOpacity(0.4),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF3949AB)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.battery_saver, color: Color(0xFF9FA8DA)),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Keep this app running in the foreground or allow '
                        'background activity for reliable attendance detection.',
                        style: TextStyle(
                            color: Color(0xFF9FA8DA), fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 32),

              // Stop button
              OutlinedButton.icon(
                onPressed: _stopAndLogout,
                icon: const Icon(Icons.stop_circle_outlined),
                label: const Text('Stop & Change Student'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.redAccent,
                  side: const BorderSide(color: Colors.redAccent),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _infoCard(
      {required String title, required List<TableRow> rows}) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFF16213E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF0F3460)),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  color: Color(0xFF4FC3F7),
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 0.8)),
          const SizedBox(height: 12),
          Table(children: rows),
        ],
      ),
    );
  }

  TableRow _row(String label, String value,
      {bool mono = false, bool wrap = false}) {
    return TableRow(children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(label,
            style: const TextStyle(color: Colors.grey, fontSize: 13)),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(
          value,
          style: TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontFamily: mono ? 'monospace' : null,
          ),
        ),
      ),
    ]);
  }
}
