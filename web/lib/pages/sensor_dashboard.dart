import 'dart:math';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import 'package:sensor_dashboard/models/initial_sensor_data.dart';
import 'package:sensor_dashboard/models/probe.dart';
import 'package:sensor_dashboard/models/sensor_data.dart';
import 'package:sensor_dashboard/services/api_exception.dart';
import 'package:sensor_dashboard/services/api_service.dart';

/// A dashboard that displays charts for a specific probe.
class SensorDashboard extends StatefulWidget {
  final Probe probe;
  final InitialSensorData initialData;
  final VoidCallback onBack;

  const SensorDashboard({
    super.key,
    required this.probe,
    required this.initialData,
    required this.onBack,
  });

  @override
  State<SensorDashboard> createState() => _SensorDashboardState();
}

class _SensorDashboardState extends State<SensorDashboard> {
  final ApiService _apiService = ApiService();

  late DateTime _startDate;
  late DateTime _endDate;
  // This is no longer a Future, but the actual data.
  List<SensorSeries> _currentSeries = [];
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _initializeFromInitialData();
  }

  /// When the widget is updated with a new probe, re-initialize its state
  /// with the new initial data provided by the parent.
  @override
  void didUpdateWidget(SensorDashboard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.probe.name != oldWidget.probe.name) {
      _initializeFromInitialData();
    }
  }

  /// Sets the state of the dashboard based on the initial data passed from the parent.
  void _initializeFromInitialData() {
    setState(() {
      _startDate = widget.initialData.startDate;
      _endDate = widget.initialData.endDate;
      _currentSeries = widget.initialData.series;
    });

    // If the initial data is empty, show the modal immediately.
    if (_currentSeries.isEmpty || _currentSeries.every((s) => s.values.isEmpty)) {
      _showNoDataDialog();
    }
  }

  /// Fetches new data based on the user's date selection.
  /// This is only called when the user manually clicks the "Search" button.
  Future<void> _fetchDataManually() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final newSeries = await _apiService.getSensorData(
        practiceId: widget.probe.name,
        startDate: _startDate,
        endDate: _endDate,
      );

      setState(() {
        _currentSeries = newSeries;
      });

      // If the manual search returns no data, show the modal.
      if (_currentSeries.isEmpty || _currentSeries.every((s) => s.values.isEmpty)) {
        _showNoDataDialog();
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error fetching data: ${e.message}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  /// Shows a dialog to inform the user that no data was found for the selected period.
  void _showNoDataDialog() {
    // Ensure the dialog is shown after the build phase is complete.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('No Data Found'),
            content: const Text('There is no sensor data available for the selected period.'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
    });
  }


  /// Displays the date picker.
  Future<void> _selectDate(BuildContext context, bool isStartDate) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: isStartDate ? _startDate : _endDate,
      firstDate: DateTime(2000),
      lastDate: DateTime(2101),
    );
    if (picked != null) {
      setState(() {
        if (isStartDate) {
          _startDate = picked;
        } else {
          _endDate = picked;
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: widget.onBack,
          tooltip: "Back to Map",
        ),
        title: Text('Probe Details: ${widget.probe.name}'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildControlPanel(),
            const SizedBox(height: 20),
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : _currentSeries.isEmpty || _currentSeries.every((s) => s.values.isEmpty)
                      ? const Center(child: Text('No data to display. Please select a different period.'))
                      : ListView.builder(
                          itemCount: _currentSeries.length,
                          itemBuilder: (context, index) {
                            return _buildChartCard(_currentSeries[index]);
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }

  /// Builds the control panel with date pickers and the search button.
  Widget _buildControlPanel() {
    final DateFormat formatter = DateFormat('yyyy-MM-dd');
    return Wrap(
      spacing: 16.0,
      runSpacing: 16.0,
      alignment: WrapAlignment.start,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        ElevatedButton.icon(
          onPressed: () => _selectDate(context, true),
          icon: const Icon(Icons.calendar_today),
          label: Text('From: ${formatter.format(_startDate)}'),
        ),
        ElevatedButton.icon(
          onPressed: () => _selectDate(context, false),
          icon: const Icon(Icons.calendar_today),
          label: Text('To: ${formatter.format(_endDate)}'),
        ),
        FilledButton.icon(
          onPressed: _fetchDataManually,
          icon: const Icon(Icons.search),
          label: const Text('Search'),
        ),
      ],
    );
  }

  /// Calculates an appropriate time interval for the chart's X-axis.
  double _getAppropriateTimeInterval(double minX, double maxX) {
    final double duration = maxX - minX;
    const double oneDay = 24 * 60 * 60 * 1000;

    if (duration <= 0) return oneDay;

    if (duration <= 2 * oneDay) {
      return 6 * 60 * 60 * 1000; // 6 hours
    } else if (duration <= 7 * oneDay) {
      return oneDay; // 1 day
    } else if (duration <= 30 * oneDay) {
      return 5 * oneDay; // 5 days
    } else {
      return 30 * oneDay; // 30 days
    }
  }
  
  /// Reduces the number of data points if there are too many to display efficiently.
  List<SensorValue> _downsampleData(List<SensorValue> data, {int maxPoints = 500}) {
    if (data.length <= maxPoints) {
      return data;
    }
    
    List<SensorValue> sampledData = [];
    double every = data.length / maxPoints;
    for (int i = 0; i < maxPoints; i++) {
      int index = (i * every).floor();
      if(index < data.length) {
        sampledData.add(data[index]);
      }
    }
    return sampledData;
  }

  /// Builds a card containing a single line chart.
  Widget _buildChartCard(SensorSeries series) {
    if (series.values.isEmpty) {
      return Card(
        margin: const EdgeInsets.only(bottom: 20),
        child: SizedBox(
          height: 380,
          child: Center(child: Text("No data available for this sensor."))
        )
      );
    }
    
    final displayData = _downsampleData(series.values);

    final double minX = displayData.map((v) => v.timestamp.millisecondsSinceEpoch.toDouble()).reduce(min);
    final double maxX = displayData.map((v) => v.timestamp.millisecondsSinceEpoch.toDouble()).reduce(max);
    final double timeInterval = _getAppropriateTimeInterval(minX, maxX);

    return Card(
      margin: const EdgeInsets.only(bottom: 20),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              series.name,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 20),
            SizedBox(
              height: 300,
              child: LineChart(
                LineChartData(
                  minX: minX,
                  maxX: maxX,
                  gridData: const FlGridData(show: true),
                  titlesData: FlTitlesData(
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 30,
                        interval: timeInterval,
                        getTitlesWidget: (value, meta) {
                          if (!value.isFinite) return const SizedBox.shrink();
                          final timestamp = DateTime.fromMillisecondsSinceEpoch(value.toInt());
                          return SideTitleWidget(
                            axisSide: meta.axisSide,
                            space: 8.0,
                            child: Text(DateFormat('MM/dd').format(timestamp)),
                          );
                        },
                      ),
                    ),
                  ),
                  borderData: FlBorderData(show: true),
                  lineBarsData: [
                    LineChartBarData(
                      spots: displayData.map((v) {
                        return FlSpot(
                          v.timestamp.millisecondsSinceEpoch.toDouble(),
                          v.value,
                        );
                      }).toList(),
                      isCurved: true,
                      color: Theme.of(context).colorScheme.primary,
                      barWidth: 3,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: false),
                      belowBarData: BarAreaData(
                        show: true,
                        color: Theme.of(context).colorScheme.primary.withOpacity(0.2),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

