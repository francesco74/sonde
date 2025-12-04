import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http_interceptor/http_interceptor.dart';
import 'package:sensor_dashboard/models/initial_sensor_data.dart';
import 'package:sensor_dashboard/models/macrogroup.dart';
import 'package:sensor_dashboard/models/sensor_data.dart';
import 'package:sensor_dashboard/services/api_exception.dart';
import 'package:sensor_dashboard/constants.dart';

/// Interceptor to inject the JWT token into headers.
class JwtInterceptor implements InterceptorContract {
  // Static token storage (in-memory). 
  // For persistence across app restarts, use flutter_secure_storage.
  static String? authToken;

  @override
  Future<BaseRequest> interceptRequest({required BaseRequest request}) async {
    request.headers['Content-Type'] = 'application/json';
    if (authToken != null) {
      request.headers['Authorization'] = 'Bearer $authToken';
    }
    return request;
  }

  @override
  Future<BaseResponse> interceptResponse({required BaseResponse response}) async {
    return response;
  }
  
  @override
  Future<bool> shouldInterceptRequest() async => true;
  
  @override
  Future<bool> shouldInterceptResponse() async => true;
}

class ApiService {
  // Use the interceptor client
  final http.Client _client = InterceptedClient.build(
    interceptors: [JwtInterceptor()],
  );

  /// Performs user login and stores the JWT token.
  Future<void> login(String username, String password) async {
    final response = await _client.post(
      Uri.parse(REST_URL_LOGIN),
      body: json.encode({'username': username, 'password': password}),
    );

    final data = json.decode(response.body);

    if (response.statusCode == 200 && data['status'] == 'ok') {
      // Store the token from the response
      JwtInterceptor.authToken = data['token'];
      return;
    }
    
    throw ApiException(
      message: data['result'] ?? 'Authentication Error',
      statusCode: response.statusCode,
    );
  }

  /// Performs user logout (clears token).
  Future<void> logout() async {
    try {
      // Optional: Call server to blacklist token if implemented
      await _client.post(Uri.parse(REST_URL_LOGOUT));
    } finally {
      JwtInterceptor.authToken = null;
    }
  }

  /// Fetches the tree of macrogroups and probes.
  Future<List<Macrogroup>> getProbes() async {
    final response = await _client.get(Uri.parse(REST_URL_GET_TREE));

    final responseData = _handleResponse(response);
    
    // Correctly cast the dynamic response to a List
    final List<dynamic> resultList = responseData['result'];
    
    return resultList.map((json) => Macrogroup.fromJson(json)).toList();
  }

  /// Fetches the latest 15 days of data.
  Future<InitialSensorData> getLatestSensorData({required String practiceId}) async {
    final uri = Uri.parse(REST_URL_GET_LATEST_DATA).replace(queryParameters: {
      'practice_id': practiceId,
    });
    final response = await _client.get(uri);

    final responseData = _handleResponse(response);
    return InitialSensorData.fromJson(responseData['data']);
  }

  /// Fetches sensor data for a specific period.
  Future<List<SensorSeries>> getSensorData({
    required String practiceId,
    required DateTime startDate,
    required DateTime endDate,
  }) async {
    final uri = Uri.parse(REST_URL_GET_DATA).replace(queryParameters: {
      'practice_id': practiceId,
      'start_date': startDate.toIso8601String().substring(0, 10),
      'end_date': endDate.toIso8601String().substring(0, 10),
    });

    final response = await _client.get(uri);

    final responseData = _handleResponse(response);
    final List<dynamic> dataList = responseData['data'];
    
    return dataList.map((json) => SensorSeries.fromJson(json)).toList();
  }

  /// Helper to handle standard API responses and errors
  dynamic _handleResponse(http.Response response) {
    final data = json.decode(response.body);
    
    if (response.statusCode == 200 && data['status'] == 'ok') {
      return data;
    } else if (response.statusCode == 401) {
      throw ApiException(
          message: 'Session expired. Please log in again.',
          statusCode: 401);
    } else if (response.statusCode == 403) {
      throw ApiException(
          message: 'Permission denied.',
          statusCode: 403);
    } else {
      throw ApiException(
          message: data['result'] ?? 'Unknown Error',
          statusCode: response.statusCode);
    }
  }
}