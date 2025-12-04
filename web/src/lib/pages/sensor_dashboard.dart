import 'dart:math';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import 'package:sensor_dashboard/models/initial_sensor_data.dart';
import 'package:sensor_dashboard/models/probe.dart';
import 'package:sensor_dashboard/models/sensor_data.dart';
import 'package:sensor_dashboard/services/api_exception.dart';
import 'package:sensor_dashboard/services/api_service.dart';

/// Enum for the data view mode.
/// Updated to include 'dataList'.
enum DataViewMode { full, dailyAverage, dataList }

/// A dashboard that displays charts or data lists for a specific probe.
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
  List<SensorSeries> _currentSeries = [];
  bool _isLoading = false;
  
  // State for the view mode
  DataViewMode _viewMode = DataViewMode.full;

  @override
  void initState() {
    super.initState();
    _initializeFromInitialData();
  }

  @override
  void didUpdateWidget(SensorDashboard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.probe.id != oldWidget.probe.id) {
      _initializeFromInitialData();
    }
  }

  void _initializeFromInitialData() {
    setState(() {
      _startDate = widget.initialData.startDate;
      _endDate = widget.initialData.endDate;
      _currentSeries = _sortSeriesByDate(widget.initialData.series);
      _viewMode = DataViewMode.full; 
    });

    if (_currentSeries.isEmpty || _currentSeries.every((s) => s.values.isEmpty)) {
      _showNoDataDialog();
    }
  }

  /// Helper to sort data points by timestamp to ensure correct chart/list rendering.
  List<SensorSeries> _sortSeriesByDate(List<SensorSeries> seriesList) {
    for (var series in seriesList) {
      series.values.sort((a, b) => a.timestamp.compareTo(b.timestamp));
    }
    return seriesList;
  }

  Future<void> _fetchDataManually() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final newSeries = await _apiService.getSensorData(
        practiceId: widget.probe.id.toString(),
        startDate: _startDate,
        endDate: _endDate,
      );

      setState(() {
        _currentSeries = _sortSeriesByDate(newSeries);
      });

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

  void _showNoDataDialog() {
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
        title: Text('Probe Details: ${widget.probe.description}'),
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
                      : ReorderableListView.builder( // CHANGED: Allow drag and drop
                          itemCount: _currentSeries.length,
                          onReorder: (int oldIndex, int newIndex) {
                             setState(() {
                               if (oldIndex < newIndex) {
                                 newIndex -= 1;
                               }
                               final SensorSeries item = _currentSeries.removeAt(oldIndex);
                               _currentSeries.insert(newIndex, item);
                             });
                          },
                          itemBuilder: (context, index) {
                            // Switch between Chart and List view based on mode
                            // Key is required for ReorderableListView
                            final key = ValueKey(_currentSeries[index].name);
                            
                            if (_viewMode == DataViewMode.dataList) {
                              return Container(
                                key: key, 
                                child: _buildDataListCard(_currentSeries[index])
                              );
                            }
                            return Container(
                                key: key,
                                child: _buildChartCard(_currentSeries[index])
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildControlPanel() {
    final DateFormat formatter = DateFormat('yyyy-MM-dd');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
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
        ),
        const SizedBox(height: 16),
        // View Mode Toggle
        SegmentedButton<DataViewMode>(
          segments: const <ButtonSegment<DataViewMode>>[
            ButtonSegment<DataViewMode>(
              value: DataViewMode.full,
              label: Text('Full Data'),
              icon: Icon(Icons.show_chart),
            ),
            ButtonSegment<DataViewMode>(
              value: DataViewMode.dailyAverage,
              label: Text('Daily Average'),
              icon: Icon(Icons.bar_chart),
            ),
            // NEW: Button for List View
            ButtonSegment<DataViewMode>(
              value: DataViewMode.dataList,
              label: Text('Data List'),
              icon: Icon(Icons.list),
            ),
          ],
          selected: <DataViewMode>{_viewMode},
          onSelectionChanged: (Set<DataViewMode> newSelection) {
            setState(() {
              _viewMode = newSelection.first;
            });
          },
        ),
      ],
    );
  }
  
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
  
  List<SensorValue> _calculateDailyAverages(List<SensorValue> data) {
    if (data.isEmpty) return [];

    final Map<String, List<double>> dailyValues = {};

    for (var point in data) {
      final String dayKey = DateFormat('yyyy-MM-dd').format(point.timestamp);
      if (!dailyValues.containsKey(dayKey)) {
        dailyValues[dayKey] = [];
      }
      dailyValues[dayKey]!.add(point.value);
    }

    final List<SensorValue> averages = [];
    dailyValues.forEach((dayKey, values) {
      final double average = values.reduce((a, b) => a + b) / values.length;
      final DateTime date = DateTime.parse(dayKey).add(const Duration(hours: 12));
      averages.add(SensorValue(timestamp: date, value: average));
    });
    
    averages.sort((a, b) => a.timestamp.compareTo(b.timestamp));
    return averages;
  }

  /// NEW: Builds a card containing a scrollable list of data points.
  Widget _buildDataListCard(SensorSeries series) {
    if (series.values.isEmpty) {
      return const SizedBox.shrink();
    }

    // Reverse order for list view so newest is at top
    final reversedValues = series.values.reversed.toList();

    return Card(
      margin: const EdgeInsets.only(bottom: 20),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  series.name,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Chip(
                  label: Text("${series.values.length} items"),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const SizedBox(height: 10),
            const Divider(),
            // Fixed height container for the list
            SizedBox(
              height: 300, 
              child: ListView.separated(
                itemCount: reversedValues.length,
                separatorBuilder: (ctx, i) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final point = reversedValues[index];
                  return ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    visualDensity: VisualDensity.compact,
                    leading: Icon(Icons.access_time, size: 16, color: Theme.of(context).colorScheme.secondary),
                    title: Text(
                      DateFormat('yyyy-MM-dd HH:mm:ss').format(point.timestamp),
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                    trailing: Text(
                      point.value.toStringAsFixed(3), // Precision format
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                        fontSize: 14,
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

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
    
    List<SensorValue> displayData;
    if (_viewMode == DataViewMode.dailyAverage) {
       displayData = _calculateDailyAverages(series.values);
    } else {
       displayData = _downsampleData(series.values);
    }

    if (displayData.isEmpty) {
       return const SizedBox.shrink();
    }

    final double minX = 0;
    final double maxX = (displayData.length - 1).toDouble();
    
    double interval = 1;
    if (displayData.length > 10) {
      interval = (displayData.length / 10).ceilToDouble();
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 20),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  series.name,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                if (_viewMode == DataViewMode.dailyAverage)
                  Chip(
                    label: const Text("Daily Avg"),
                    backgroundColor: Theme.of(context).colorScheme.secondaryContainer,
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              height: 350, 
              child: LineChart(
                LineChartData(
                  lineTouchData: LineTouchData(
                    enabled: true,
                    handleBuiltInTouches: true,
                    touchSpotThreshold: 20, 
                    distanceCalculator: (touchPoint, spotPixelCoordinates) {
                      final xDistance = (touchPoint.dx - spotPixelCoordinates.dx).abs();
                      final yDistance = (touchPoint.dy - spotPixelCoordinates.dy).abs();
                      return xDistance + (yDistance / 5); 
                    },
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipItems: (List<LineBarSpot> touchedBarSpots) {
                        return touchedBarSpots.map((barSpot) {
                          final flSpot = barSpot;
                          final index = flSpot.x.toInt();
                          if (index < 0 || index >= displayData.length) return null;

                          final timestamp = displayData[index].timestamp;
                          
                          String dateStr;
                          if (_viewMode == DataViewMode.full) {
                             dateStr = DateFormat('MM/dd HH:mm').format(timestamp);
                          } else {
                             dateStr = DateFormat('yyyy-MM-dd').format(timestamp);
                          }
                          
                          return LineTooltipItem(
                            '$dateStr \n${flSpot.y.toStringAsFixed(2)}',
                            const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          );
                        }).toList();
                      },
                    ),
                  ),
                  
                  minX: minX,
                  maxX: maxX,
                  gridData: FlGridData(
                    show: true,
                    drawVerticalLine: true,
                    horizontalInterval: null,
                    verticalInterval: interval,
                    getDrawingVerticalLine: (value) {
                         return FlLine(
                           color: Theme.of(context).colorScheme.outlineVariant.withOpacity(0.5),
                           strokeWidth: 1,
                         );
                    },
                  ),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true, 
                        reservedSize: 60,
                      ),
                    ),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 60,
                        interval: interval,
                        getTitlesWidget: (value, meta) {
                          final index = value.round();
                          if (index < 0 || index >= displayData.length) return const SizedBox.shrink();

                          final timestamp = displayData[index].timestamp;
                          
                          String formattedDate;
                          if (_viewMode == DataViewMode.full) {
                            formattedDate = DateFormat('MM/dd HH:mm').format(timestamp);
                          } else {
                            formattedDate = DateFormat('MM/dd').format(timestamp);
                          }

                          return SideTitleWidget(
                            axisSide: meta.axisSide,
                            space: 10.0,
                            angle: -1.5708,
                            child: Padding(
                              padding: const EdgeInsets.only(top: 12.0),
                              child: Text(
                                formattedDate, 
                                style: const TextStyle(fontSize: 10),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  borderData: FlBorderData(show: true),
                  lineBarsData: [
                    LineChartBarData(
                      spots: displayData.asMap().entries.map((e) {
                        return FlSpot(
                          e.key.toDouble(),
                          e.value.value,
                        );
                      }).toList(),
                      isCurved: _viewMode == DataViewMode.full,
                      color: Theme.of(context).colorScheme.primary,
                      barWidth: 3,
                      isStrokeCapRound: true,
                      dotData: FlDotData(
                        show: _viewMode == DataViewMode.dailyAverage,
                      ),
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