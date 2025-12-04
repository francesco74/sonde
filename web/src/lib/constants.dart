import 'dart:js_interop';

@JS('ENV_CONFIG')
external EnvConfigJS? get envConfigJS;

@JS()
extension type EnvConfigJS._(JSObject _) implements JSObject {
  external String? get REST_URL;
}


class EnvConfig {
  static const String _defaultRestUrl = 'http://localhost:5000';
  
  static String get restUrl {
    // Read from JavaScript first (Runtime value)
    final runtimeValue = envConfigJS?.REST_URL;
    
    // If the runtime value is missing or null, fall back to the safe default
    return runtimeValue ?? _defaultRestUrl;
  }
}

// For convenience, you can keep your original constant names
final String REST_URL = EnvConfig.restUrl;
final String REST_URL_LOGIN = '$REST_URL/login';
final String REST_URL_LOGOUT = '$REST_URL/logout';
final String REST_URL_GET_TREE = '$REST_URL/get_tree';
final String REST_URL_GET_LATEST_DATA = '$REST_URL/get_latest_data';
final String REST_URL_GET_DATA = '$REST_URL/get_data';

