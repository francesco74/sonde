import 'package:flutter/material.dart';
import 'package:sensor_dashboard/pages/login_page.dart';

void main() {
  // NOTA: Per eseguire questa app e connetterla a un server locale (come il server.py di esempio),
  // devi disabilitare la sicurezza web del browser a causa delle policy CORS.
  // Esegui l'app con il seguente comando nel terminale:
  // flutter run -d chrome --web-browser-flag "--disable-web-security"
  runApp(const SensorApp());
}

class SensorApp extends StatelessWidget {
  const SensorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Dashboard Sensori',
      theme: ThemeData(
        primarySwatch: Colors.indigo,
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF1a1a2e),
        cardColor: const Color(0xFF16213e),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(color: Colors.white70),
          titleLarge: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          titleMedium: TextStyle(color: Colors.white),
        ),
        inputDecorationTheme: InputDecorationTheme(
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white24)),
            labelStyle: const TextStyle(color: Colors.white70)),
      ),
      home: const LoginPage(),
      debugShowCheckedModeBanner: false,
    );
  }
}
