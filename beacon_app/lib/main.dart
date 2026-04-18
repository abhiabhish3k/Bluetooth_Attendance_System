import 'package:flutter/material.dart';

import 'services/beacon_service.dart';
import 'screens/login_screen.dart';
import 'screens/beacon_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BleAttendanceApp());
}

class BleAttendanceApp extends StatelessWidget {
  const BleAttendanceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BLE Attendance',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0288D1),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const _Splash(),
    );
  }
}

/// Splash/boot screen: loads saved config and routes to the right screen.
class _Splash extends StatefulWidget {
  const _Splash();

  @override
  State<_Splash> createState() => _SplashState();
}

class _SplashState extends State<_Splash> {
  final BeaconService _service = BeaconService();

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    await _service.initForegroundTask();
    await _service.loadConfig();

    if (!mounted) return;

    if (_service.config != null) {
      // Saved config found – go straight to the beacon screen
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => BeaconScreen(
            beaconService: _service,
            config: _service.config!,
          ),
        ),
      );
    } else {
      // No config – show login
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => LoginScreen(beaconService: _service),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF1A1A2E),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.bluetooth_searching,
                size: 80, color: Color(0xFF4FC3F7)),
            SizedBox(height: 24),
            CircularProgressIndicator(color: Color(0xFF4FC3F7)),
          ],
        ),
      ),
    );
  }
}
