import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/student_config.dart';
import '../services/beacon_service.dart';
import 'beacon_screen.dart';

/// Login / configuration screen.
///
/// The student enters their unique numeric ID (assigned by the teacher/admin).
/// This ID corresponds to the iBeacon Minor field and is registered in the
/// backend via POST /api/students/{id}/beacon/register.
class LoginScreen extends StatefulWidget {
  final BeaconService beaconService;

  const LoginScreen({super.key, required this.beaconService});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _idController = TextEditingController();
  final _uuidController = TextEditingController(text: BeaconDefaults.uuid);
  final _majorController =
      TextEditingController(text: BeaconDefaults.major.toString());

  bool _showAdvanced = false;

  @override
  void initState() {
    super.initState();
    _prefillFromSaved();
  }

  Future<void> _prefillFromSaved() async {
    await widget.beaconService.loadConfig();
    final cfg = widget.beaconService.config;
    if (cfg != null && mounted) {
      setState(() {
        _nameController.text = cfg.studentName;
        _idController.text = cfg.beaconMinor.toString();
        _uuidController.text = cfg.beaconUuid;
        _majorController.text = cfg.beaconMajor.toString();
      });
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _idController.dispose();
    _uuidController.dispose();
    _majorController.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;

    final minor = int.parse(_idController.text.trim());
    final major = int.tryParse(_majorController.text.trim()) ?? BeaconDefaults.major;
    final uuid = _uuidController.text.trim().isEmpty
        ? BeaconDefaults.uuid
        : _uuidController.text.trim();

    final config = StudentConfig(
      studentId: _idController.text.trim(),
      studentName: _nameController.text.trim(),
      beaconMinor: minor,
      beaconUuid: uuid,
      beaconMajor: major,
    );

    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => BeaconScreen(
          beaconService: widget.beaconService,
          config: config,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 40),
                // Logo / title
                const Icon(Icons.bluetooth_searching,
                    size: 72, color: Color(0xFF4FC3F7)),
                const SizedBox(height: 16),
                const Text(
                  'BLE Attendance',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
                const Text(
                  'Student Beacon App',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 16, color: Color(0xFF90CAF9)),
                ),
                const SizedBox(height: 48),

                // Name field
                TextFormField(
                  controller: _nameController,
                  style: const TextStyle(color: Colors.white),
                  decoration: _inputDecoration('Your Name', Icons.person),
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Enter your name' : null,
                ),
                const SizedBox(height: 16),

                // Beacon ID field (numeric)
                TextFormField(
                  controller: _idController,
                  style: const TextStyle(color: Colors.white),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: _inputDecoration(
                      'Beacon ID (given by admin)', Icons.badge),
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) {
                      return 'Enter your beacon ID';
                    }
                    final n = int.tryParse(v.trim());
                    if (n == null || n < 0 || n > 65535) {
                      return 'Beacon ID must be 0–65535';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 24),

                // Advanced settings toggle
                TextButton.icon(
                  onPressed: () =>
                      setState(() => _showAdvanced = !_showAdvanced),
                  icon: Icon(
                    _showAdvanced ? Icons.expand_less : Icons.expand_more,
                    color: const Color(0xFF90CAF9),
                  ),
                  label: const Text(
                    'Advanced Settings',
                    style: TextStyle(color: Color(0xFF90CAF9)),
                  ),
                ),

                if (_showAdvanced) ...[
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _uuidController,
                    style: const TextStyle(color: Colors.white),
                    decoration: _inputDecoration('Beacon UUID', Icons.tag),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _majorController,
                    style: const TextStyle(color: Colors.white),
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: _inputDecoration('Major (class ID)', Icons.class_),
                    validator: (v) {
                      if (v == null || v.isEmpty) return null;
                      final n = int.tryParse(v);
                      if (n == null || n < 0 || n > 65535) {
                        return 'Major must be 0–65535';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                ],

                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: _submit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF0288D1),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text('Start Broadcasting',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(String label, IconData icon) =>
      InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: Color(0xFF90CAF9)),
        prefixIcon: Icon(icon, color: const Color(0xFF4FC3F7)),
        filled: true,
        fillColor: const Color(0xFF16213E),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF0F3460)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF4FC3F7)),
        ),
      );
}
