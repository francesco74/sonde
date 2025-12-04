/// Model for a single probe.
class Probe {
  final int id; // ID is an integer in the database
  final String description;
  final double latitude;
  final double longitude;

  Probe({
    required this.id,
    required this.description,
    required this.latitude,
    required this.longitude,
  });

  /// Creates a Probe instance from a JSON object.
  factory Probe.fromJson(Map<String, dynamic> json) {
    return Probe(
      id: int.parse(json['id'].toString()), 
      description: json['description'],
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
    );
  }
}