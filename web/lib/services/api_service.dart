import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http/browser_client.dart';
import 'package:sensor_dashboard/models/initial_sensor_data.dart';
import 'package:sensor_dashboard/models/macrogroup.dart';
import 'package:sensor_dashboard/models/probe.dart';
import 'package:sensor_dashboard/models/sensor_data.dart';
import 'package:sensor_dashboard/services/api_exception.dart';
import 'package:sensor_dashboard/utils/constants.dart';

class ApiService {
  final http.Client _client = BrowserClient()..withCredentials = true;

  /// Performs user login.
  Future<void> login(String username, String password) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/login'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'username': username, 'password': password}),
    );

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      if (data['status'] == 'ok') {
        return;
      }
    }
    final data = json.decode(response.body);
    throw ApiException(
      message: data['result'] ?? 'Authentication Error',
      statusCode: response.statusCode,
    );
  }

  /// Performs user logout.
  Future<void> logout() async {
    await _client.post(Uri.parse('$baseUrl/logout'));
  }

  /// Fetches the tree of macrogroups and probes for the logged-in user.
  Future<List<Macrogroup>> getProbes() async {
    final response = await _client.get(Uri.parse('$baseUrl/get_tree'));

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      if (data['status'] == 'ok') {
        final List<dynamic> resultList = data['result'];
        return resultList.map((json) => Macrogroup.fromJson(json)).toList();
      } else {
        throw ApiException(message: data['result']);
      }
    } else if (response.statusCode == 401) {
      throw ApiException(
          message: 'Session expired. Please log in again.',
          statusCode: 401);
    } else {
      throw ApiException(
          message: 'Error fetching the practice tree',
          statusCode: response.statusCode);
    }
  }

  /// Fetches the latest 15 days of data for a specific probe.
  /// Assumes a new endpoint '/get_latest_data'.
  Future<InitialSensorData> getLatestSensorData({
    required String practiceId,
  }) async {
    final uri = Uri.parse('$baseUrl/get_latest_data').replace(queryParameters: {
      'practice_id': practiceId,
    });

    final response = await _client.get(uri);

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      if (data['status'] == 'ok') {
        // The actual data is nested under a 'data' key in the response
        return InitialSensorData.fromJson(data['data']);
      } else {
        throw ApiException(message: data['result']);
      }
    } else if (response.statusCode == 401) {
      throw ApiException(
          message: 'Session expired. Please log in again.',
          statusCode: 401);
    } else {
      throw ApiException(
          message: 'Error fetching latest sensor data',
          statusCode: response.statusCode);
    }
  }

  /// Fetches sensor data for a specific probe within a given date range.
  Future<List<SensorSeries>> getSensorData({
    required String practiceId,
    required DateTime startDate,
    required DateTime endDate,
  }) async {
    final uri = Uri.parse('$baseUrl/get_data').replace(queryParameters: {
      'practice_id': practiceId,
      'start_date': startDate.toIso8601String().split('T').first,
      'end_date': endDate.toIso8601String().split('T').first,
    });

    final response = await _client.get(uri);

    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      if (data['status'] == 'ok') {
        final List<dynamic> dataList = data['data'];
        return dataList.map((json) => SensorSeries.fromJson(json)).toList();
      } else {
        throw ApiException(message: data['result']);
      }
    } else if (response.statusCode == 401) {
      throw ApiException(
          message: 'Session expired. Please log in again.',
          statusCode: 401);
    } else if (response.statusCode == 403) {
      throw ApiException(
          message: 'You do not have permission to view data for this probe.',
          statusCode: 403);
    } else {
      throw ApiException(
          message: 'Error fetching sensor data',
          statusCode: response.statusCode);
    }
  }
}

