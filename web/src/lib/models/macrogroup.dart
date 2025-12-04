import 'package:sensor_dashboard/models/probe.dart';

/// Model for a macrogroup, which contains multiple probes.
class Macrogroup {
  final String id;
  final String description;
  final List<Probe> probes;

  Macrogroup({
    required this.id, 
    required this.description, 
    required this.probes
  });

  factory Macrogroup.fromJson(Map<String, dynamic> json) {
    var probesList = json['probes'] as List;
    List<Probe> probeObjects =
        probesList.map((i) => Probe.fromJson(i)).toList();
        
    return Macrogroup(
      // Map the new JSON keys
      id: json['macrogroup_id'],
      description: json['macrogroup_description'] ?? '',
      probes: probeObjects,
    );
  }
}