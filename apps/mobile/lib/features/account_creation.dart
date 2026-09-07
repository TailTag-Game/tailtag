import "package:flutter/material.dart";

class AccountCreationScreen extends StatefulWidget {
  const AccountCreationScreen({super.key});

  @override
  State<AccountCreationScreen> createState() => _AccountCreationScreenState();
}

class _AccountCreationScreenState extends State<AccountCreationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _passwordController = TextEditingController();
  String _userEmail = "";
  String _userUsername = "";
  String _userPassword = "";
  bool _isSaving = false;

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Create new account")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            spacing: 32.0,
            children: [
              Text(
                "Welcome in.",
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
                        labelText: "Username",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Username is required.";
                        }
                        // TODO: Handle server callback
                        return null;
                      },
                      onSaved: (value) {
                        _userUsername = value!;
                      },
                    ),
                    TextFormField(
                      decoration: const InputDecoration(
                        labelText: "Email",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Email is required.";
                        }
                        if (!RegExp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
                            .hasMatch(value)) {
                          return "A valid email is required.";
                        }
                        return null;
                      },
                      onSaved: (value) {
                        _userEmail = value!;
                      },
                    ),
                    TextFormField(
                      decoration: const InputDecoration(
                        labelText: "Password",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      controller: _passwordController,
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
                    TextFormField(
                      decoration: const InputDecoration(
                        labelText: "Confirm password",
                        border: OutlineInputBorder(),
                        floatingLabelBehavior: FloatingLabelBehavior.always,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Password is required.";
                        }
                        if (value != _passwordController.text) {
                          return "Password does not match.";
                        }
                        return null;
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
                        ) : const Text("Create Account")
                      ),
                    )
                  ],
                ),
              ),
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
    _userEmail = "";
    _userUsername = "";
    _userPassword = "";
  }
}
