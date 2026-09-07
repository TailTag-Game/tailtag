import "package:flutter/material.dart";

// TODO: Make shared architecture for login and creation; DRY.

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();

  String _userLogin = "";
  String _userPassword = "";
  bool _isSaving = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Login")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            spacing: 32.0,
            children: [
              Text(
                "Welcome back.",
                style: Theme.of(context).textTheme.displayMedium,
              ),
              Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 16,
                  children: [
                    TextFormField(
                      decoration: const InputDecoration(
                        labelText: "Username or email",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Username or email is required.";
                        }
                        // TODO: Handle server callback
                        return null;
                      },
                      onSaved: (value) {
                        _userLogin = value!;
                      },
                    ),TextFormField(
                      decoration: const InputDecoration(
                        labelText: "Password",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Password is required.";
                        }
                        return null;
                      },
                      onSaved: (value) {
                        _userPassword = value!;
                      },
                    ),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                          onPressed: _isSaving ? null : () => _submit(context),
                          child: _isSaving
                              ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2)
                          ) : const Text("Sign in")
                      ),
                    )
                  ],
                )
              )
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit(BuildContext context) async {
    setState(() => _isSaving = true);
    try {
      if (_formKey.currentState!.validate()) {
        // TODO: Add server code
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).clearSnackBars();
        // TODO: Remove snackbar once other mechanisms are in place.
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text("Account created.")));
        _formKey.currentState!.reset();
        resetStateVariables();
      }
    }
    finally {
      if (context.mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  void resetStateVariables() {
    _userPassword = "";
    _userPassword = "";
  }

}
