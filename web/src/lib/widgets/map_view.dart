import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sensor_dashboard/models/probe.dart';

/// A custom TileProvider that uses standard Image.network behavior
/// to avoid cancellation issues on Flutter Web during rapid zooming.
class WebTileProvider extends TileProvider {
  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    return NetworkImage(getTileUrl(coordinates, options));
  }
}

class MapView extends StatefulWidget {
  final List<Probe> probes;
  final Function(Probe) onMarkerTap;

  const MapView({super.key, required this.probes, required this.onMarkerTap});

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> {
  // Controller to manipulate the map state programmatically
  final MapController _mapController = MapController();

  // Default center (Lucca, Tuscany)
  static const LatLng _initialCenter = LatLng(43.8429, 10.5029);
  static const double _initialZoom = 12.0;

  @override
  Widget build(BuildContext context) {
    // Create markers for each probe
    final List<Marker> markers = widget.probes.map((probe) {
      return Marker(
        width: 80.0,
        height: 80.0,
        point: LatLng(probe.latitude, probe.longitude),
        child: GestureDetector(
          onTap: () => widget.onMarkerTap(probe),
          child: Tooltip(
            message: probe.description,
            child: Icon(
              Icons.location_pin,
              color: Colors.red, // Explicit red color
              size: 45.0,
            ),
          ),
        ),
      );
    }).toList();

    return Stack(
      children: [
        FlutterMap(
          mapController: _mapController,
          options: const MapOptions(
            initialCenter: _initialCenter,
            initialZoom: _initialZoom,
            // Disable rotation to keep labels aligned
            interactionOptions: InteractionOptions(
              flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
            ),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.example.sensor_dashboard',
              // FIX: Use the custom WebTileProvider to completely bypass
              // the CancellableNetworkTileProvider logic causing crashes on web.
              tileProvider: WebTileProvider(),
            ),
            MarkerLayer(markers: markers),
          ],
        ),
        // Zoom Controls
        Positioned(
          bottom: 20,
          right: 20,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              FloatingActionButton(
                heroTag: 'zoom_in',
                mini: true,
                onPressed: () {
                  _mapController.move(
                    _mapController.camera.center,
                    _mapController.camera.zoom + 1,
                  );
                },
                child: const Icon(Icons.add),
              ),
              const SizedBox(height: 10),
              FloatingActionButton(
                heroTag: 'zoom_out',
                mini: true,
                onPressed: () {
                  _mapController.move(
                    _mapController.camera.center,
                    _mapController.camera.zoom - 1,
                  );
                },
                child: const Icon(Icons.remove),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
