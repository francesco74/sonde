import 'package:sensor_dashboard/models/probe.dart';

/// Model for a macrogroup, which contains multiple probes.
class Macrogroup {
  final String name;
  final List<Probe> probes;

  Macrogroup({required this.name, required this.probes});

  /// Creates a Macrogroup instance from a JSON object.
  /// This factory now correctly maps the keys from the server's response.
  factory Macrogroup.fromJson(Map<String, dynamic> json) {
    // Reads the list from the 'probes' key in the JSON
    var probesList = json['probes'] as List;
    List<Probe> probeObjects =
        probesList.map((i) => Probe.fromJson(i)).toList();
        
    return Macrogroup(
      // Reads the name from the 'macrogroup_name' key in the JSON
      name: json['macrogroup_name'],
      probes: probeObjects,
    );
  }
}

