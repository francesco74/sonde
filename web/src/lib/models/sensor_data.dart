/// Model for a series of sensor data (e.g., "Temperature").
class SensorSeries {
  final String name;
  final List<SensorValue> values;

  SensorSeries({required this.name, required this.values});

  /// Creates a SensorSeries instance from a JSON object.
  factory SensorSeries.fromJson(Map<String, dynamic> json) {
    var valuesList = json['values'] as List;
    List<SensorValue> sensorValues =
        valuesList.map((i) => SensorValue.fromJson(i)).toList();
    return SensorSeries(
      name: json['name'],
      values: sensorValues,
    );
  }
}

/// Model for a single data point (value and timestamp).
class SensorValue {
  final DateTime timestamp;
  final double value;

  SensorValue({required this.timestamp, required this.value});

  /// Creates a SensorValue instance from a JSON object.
  factory SensorValue.fromJson(Map<String, dynamic> json) {
    return SensorValue(
      // CORRECTED: The server sends milliseconds (13 digits), so we use it directly.
      // Previously, we were multiplying by 1000, which caused incorrect dates.
      timestamp: DateTime.fromMillisecondsSinceEpoch(json['timestamp']),
      value: (json['value'] as num).toDouble(),
    );
  }
}