# TailTag App

[//]: # (TODO: Synopsis)

The app uses FVM to manage Flutter, the current version being 3.47.1, and its associated Dart version, the Flutter build system (which ultimately uses the native build systems of Gradle on Android and Xcode on iOS), the flutter_test system, and dartdoc.

## Development Setup
Android Studio is the recommended IDE for this project. Android Studio, IntelliJ, and Visual Studio Code all have mature plugins for Flutter.

### Installing Android Studio
You can either [install the program itself](https://developer.android.com/studio), or use JetBrains [Toolbox App](https://www.jetbrains.com/toolbox-app/). Toolbox App provides an easy way to update the IDE. 

### Setting up Environment
1. This project uses FVM to manage Flutter versions. Follow the installation instructions for your platform [here](https://fvm.app/install.sh). Once installed (you may need to restart your IDE, or even your computer for the PATH changes to take effect), run `fvm install` to install the current version required by the project.
2. [Install the Flutter plugin](https://fvm.app/install.sh) (IMPORTANT: Stop reading at the "Creating projects" header)
3. Go to Settings > Languages & Frameworks > Flutter > Flutter SDK Path. Select $PROJECT_DIR/.fvm/flutter_sdk. Repeat this step as needed (when Studio can no longer find the SDK).

## Documentation
All code documentation will happen via dartdoc. Docstrings are written with ///. Use `fvm dart doc` to generate documents. If you'd like to see a local version of your doc changes, run `fvm exec dhttpd --path doc/api`
