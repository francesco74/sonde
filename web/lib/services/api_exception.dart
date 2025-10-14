/// Eccezione personalizzata per rappresentare errori specifici dell'API.
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  // CORRETTO: Convertito a un costruttore con parametri nominativi.
  ApiException({required this.message, this.statusCode});

  @override
  String toString() {
    if (statusCode != null) {
      return 'ApiException (Status $statusCode): $message';
    }
    return 'ApiException: $message';
  }
}