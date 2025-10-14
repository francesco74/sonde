class Probe {
  final String name;
  final String description;
  final double latitude;
  final double longitude;

  Probe({
    required this.name,
    required this.description,
    required this.latitude,
    required this.longitude,
  });

  factory Probe.fromJson(Map<String, dynamic> json) {
    return Probe(
      name: json['name'] ?? 'N/A',
      description: json['description'] ?? 'N/A',
      latitude: (json['latitude'] as num? ?? 0.0).toDouble(),
      longitude: (json['longitude'] as num? ?? 0.0).toDouble(),
    );
  }
}
