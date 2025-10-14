/// Modello per una serie di dati di un sensore (es. "Temperatura").
class SensorSeries {
  final String name;
  final List<SensorValue> values;

  SensorSeries({required this.name, required this.values});

  /// Crea un'istanza di SensorSeries da un oggetto JSON.
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

/// Modello per un singolo punto dati (valore e timestamp).
class SensorValue {
  final DateTime timestamp;
  final double value;

  SensorValue({required this.timestamp, required this.value});

  /// Crea un'istanza di SensorValue da un oggetto JSON.
  factory SensorValue.fromJson(Map<String, dynamic> json) {
    return SensorValue(
      // CORREZIONE: Il server invia i secondi, ma DateTime.fromMillisecondsSinceEpoch
      // si aspetta i millisecondi. Moltiplichiamo per 1000 per la conversione.
      timestamp: DateTime.fromMillisecondsSinceEpoch(json['timestamp'] * 1000),
      value: (json['value'] as num).toDouble(),
    );
  }
}

