import 'package:flutter/material.dart';
import 'package:sensor_dashboard/models/initial_sensor_data.dart';
import 'package:sensor_dashboard/models/macrogroup.dart';
import 'package:sensor_dashboard/models/probe.dart';
import 'package:sensor_dashboard/pages/login_page.dart';
import 'package:sensor_dashboard/pages/sensor_dashboard.dart';
import 'package:sensor_dashboard/services/api_exception.dart';
import 'package:sensor_dashboard/services/api_service.dart';
import 'package:sensor_dashboard/widgets/map_view.dart';

/// The main page that manages the two-column layout
/// and navigation between the map and the sensor dashboard.
class MainLayoutPage extends StatefulWidget {
  const MainLayoutPage({super.key});

  @override
  State<MainLayoutPage> createState() => _MainLayoutPageState();
}

class _MainLayoutPageState extends State<MainLayoutPage> {
  final ApiService _apiService = ApiService();
  late Future<List<Macrogroup>> _probesFuture;

  // This state will hold the initial data for the selected probe
  InitialSensorData? _initialSensorData;
  Probe? _selectedProbe;
  bool _isLoadingProbeData = false;

  @override
  void initState() {
    super.initState();
    _loadProbes();
  }

  void _loadProbes() {
    setState(() {
       _probesFuture = _apiService.getProbes();
    });
  }

  /// Handles the selection of a new probe from the list or map.
  /// It triggers the fetching of the latest 15 days of data.
  Future<void> _handleProbeSelection(Probe probe) async {
    // Avoid reloading if the same probe is selected again
    if (_selectedProbe?.name == probe.name) return;

    setState(() {
      _selectedProbe = probe;
      _isLoadingProbeData = true; // Show loading indicator in the right pane
      _initialSensorData = null; // Clear previous data
    });

    try {
      final initialData = await _apiService.getLatestSensorData(practiceId: probe.name);
      if (mounted) {
        setState(() {
          _initialSensorData = initialData;
          _isLoadingProbeData = false;
        });
      }
    } on ApiException catch (e) {
       if (mounted) {
         setState(() { _isLoadingProbeData = false; });
         // Show an error message if the initial data fetch fails
         ScaffoldMessenger.of(context).showSnackBar(
           SnackBar(
             content: Text('Error loading initial data: ${e.message}'),
             backgroundColor: Colors.red,
           ),
         );
       }
    }
  }


  void _handleBackToMap() {
    setState(() {
      _selectedProbe = null;
      _initialSensorData = null;
    });
  }
  
  Future<void> _logout() async {
    try {
      await _apiService.logout();
    } catch (e) {
      // Ignore errors during logout, always navigate to the login page
    } finally {
      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (context) => const LoginPage()),
        );
      }
    }
  }


  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Probe Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: _logout,
          ),
        ],
      ),
      body: FutureBuilder<List<Macrogroup>>(
        future: _probesFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
             final error = snapshot.error;
             String errorMessage = 'An unexpected error occurred.';

             if (error is ApiException && error.statusCode == 401) {
                // If session expired, redirect to login
                WidgetsBinding.instance.addPostFrameCallback((_) {
                   if(mounted) {
                     Navigator.of(context).pushReplacement(
                       MaterialPageRoute(builder: (context) => const LoginPage()),
                     );
                   }
                });
                errorMessage = 'Session expired. Redirecting to login...';
             } else if (error is ApiException) {
                errorMessage = 'API Error (${error.statusCode}): ${error.message}';
             } else {
                errorMessage = error.toString();
             }
             
             return Center(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 60),
                      const SizedBox(height: 16),
                      Text(
                        'Failed to Load Data',
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Colors.red),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        errorMessage,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ],
                  ),
                ),
              );
          }
          if (snapshot.hasData && snapshot.data!.isNotEmpty) {
            final macrogroups = snapshot.data!;
            // Extract all probes from all macrogroups for the map
            final allProbes = macrogroups.expand((mg) => mg.probes).toList();

            return Row(
              children: [
                // Left Column: Probe List
                SizedBox(
                  width: 300,
                  child: ListView.builder(
                    itemCount: macrogroups.length,
                    itemBuilder: (context, index) {
                      final macrogroup = macrogroups[index];
                      return ExpansionTile(
                        title: Text(macrogroup.name, style: const TextStyle(fontWeight: FontWeight.bold)),
                        initiallyExpanded: true,
                        children: macrogroup.probes.map((probe) {
                          return ListTile(
                            title: Text(probe.name),
                            subtitle: Text(probe.description),
                            selected: _selectedProbe?.name == probe.name,
                            onTap: () => _handleProbeSelection(probe),
                          );
                        }).toList(),
                      );
                    },
                  ),
                ),
                const VerticalDivider(width: 1),
                // Right Column: Map or Dashboard
                Expanded(
                  child: _buildRightPane(allProbes),
                ),
              ],
            );
          }
          return const Center(child: Text('No probes found.'));
        },
      ),
    );
  }

  /// Builds the right pane, showing the map, a loading indicator,
  /// or the sensor dashboard based on the current state.
  Widget _buildRightPane(List<Probe> allProbes) {
    if (_selectedProbe == null) {
      // No probe is selected, show the map
      return MapView(
        probes: allProbes,
        onMarkerTap: _handleProbeSelection,
      );
    } else if (_isLoadingProbeData) {
      // A probe is selected, but we are fetching its initial data
      return const Center(child: CircularProgressIndicator());
    } else if (_initialSensorData != null) {
      // A probe is selected and we have its initial data
      return SensorDashboard(
        probe: _selectedProbe!,
        initialData: _initialSensorData!,
        onBack: _handleBackToMap,
      );
    } else {
      // A probe is selected, but data fetching failed or hasn't completed
      return const Center(
        child: Text("Select a probe to view its data."),
      );
    }
  }
}

