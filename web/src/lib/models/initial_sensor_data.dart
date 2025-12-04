import 'package:sensor_dashboard/models/sensor_data.dart';

/// Represents the initial data payload for a probe,
/// including the date range and the list of sensor series.
class InitialSensorData {
  final DateTime startDate;
  final DateTime endDate;
  final List<SensorSeries> series;

  InitialSensorData({
    required this.startDate,
    required this.endDate,
    required this.series,
  });

  /// Creates an instance from a JSON object.
  /// Assumes the server sends dates in 'YYYY-MM-DD' format.
  factory InitialSensorData.fromJson(Map<String, dynamic> json) {
    var seriesList = json['series'] as List;
    List<SensorSeries> sensorSeries =
        seriesList.map((i) => SensorSeries.fromJson(i)).toList();
    
    return InitialSensorData(
      startDate: DateTime.parse(json['startDate']),
      endDate: DateTime.parse(json['endDate']),
      series: sensorSeries,
    );
  }
}
