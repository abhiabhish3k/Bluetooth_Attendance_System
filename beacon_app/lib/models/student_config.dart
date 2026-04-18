/// Student configuration model stored in SharedPreferences.
class StudentConfig {
  final String studentId;
  final String studentName;
  final int beaconMinor;
  final String beaconUuid;
  final int beaconMajor;
  final int txPower;

  const StudentConfig({
    required this.studentId,
    required this.studentName,
    required this.beaconMinor,
    this.beaconUuid = BeaconDefaults.uuid,
    this.beaconMajor = BeaconDefaults.major,
    this.txPower = BeaconDefaults.txPower,
  });

  /// The beacon_id sent to the backend – "<major>:<minor>" format.
  String get beaconId => '$beaconMajor:$beaconMinor';

  Map<String, dynamic> toMap() => {
        'studentId': studentId,
        'studentName': studentName,
        'beaconMinor': beaconMinor,
        'beaconUuid': beaconUuid,
        'beaconMajor': beaconMajor,
        'txPower': txPower,
      };

  factory StudentConfig.fromMap(Map<String, dynamic> map) => StudentConfig(
        studentId: map['studentId'] as String,
        studentName: map['studentName'] as String? ?? '',
        beaconMinor: map['beaconMinor'] as int,
        beaconUuid: map['beaconUuid'] as String? ?? BeaconDefaults.uuid,
        beaconMajor: map['beaconMajor'] as int? ?? BeaconDefaults.major,
        txPower: map['txPower'] as int? ?? BeaconDefaults.txPower,
      );
}

/// Institution-wide beacon defaults.
abstract class BeaconDefaults {
  /// Fixed UUID for this institution – must match scanner config.
  static const String uuid = 'A8B3F9E2-C4D5-4F6A-7B8C-9D0E1F2A3B4C';

  /// Major field – identifies the institution/class.
  static const int major = 1;

  /// Default TX power in dBm (used for distance estimation).
  static const int txPower = -59;
}
