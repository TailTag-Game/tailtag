import 'package:flutter/material.dart';

/// This is an example docstring.
void main() {
  runApp(const MainApp());
}

/// This is the Main App widget. It displays Hello World in the center of the screen.
class MainApp extends StatelessWidget {
  const MainApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      home: Scaffold(
        body: Center(
          child: Text('Hello World!'),
        ),
      ),
    );
  }
}
