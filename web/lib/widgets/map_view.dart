import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sensor_dashboard/models/probe.dart';

class MapView extends StatelessWidget {
  final List<Probe> probes;
  final Function(Probe) onMarkerTap;

  const MapView({super.key, required this.probes, required this.onMarkerTap});

  @override
  Widget build(BuildContext context) {
    // Lista di marker da visualizzare sulla mappa
    final List<Marker> markers = probes.map((probe) {
      return Marker(
        width: 80.0,
        height: 80.0,
        point: LatLng(probe.latitude, probe.longitude),
        child: GestureDetector(
          onTap: () => onMarkerTap(probe),
          child: Tooltip(
            message: "${probe.name}\n${probe.description}",
            child: Icon(
              Icons.location_pin,
              color: Theme.of(context).colorScheme.primary,
              size: 45.0,
            ),
          ),
        ),
      );
    }).toList();

    return FlutterMap(
      options: const MapOptions(
        // Centro iniziale della mappa (Lucca, Toscana)
        initialCenter: LatLng(43.8429, 10.5029),
        initialZoom: 12.0,
      ),
      children: [
        // Layer che disegna la mappa di base da OpenStreetMap
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.example.sensor_dashboard',
        ),
        // Layer che disegna i marker delle sonde
        MarkerLayer(markers: markers),
      ],
    );
  }
}
