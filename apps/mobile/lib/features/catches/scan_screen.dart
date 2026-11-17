import "dart:async";

import "package:flutter/material.dart";
import "package:flutter/semantics.dart";
import "package:flutter/services.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/catches/camera_permission.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/catches/qr_scanner.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";
import "package:tailtag_mobile/features/catches/catches_controller.dart";
import "package:tailtag_mobile/features/catches/requests_controller.dart";
import "package:tailtag_mobile/features/catches/scan_controller.dart";

/// The full-screen scanner: camera, preview, confirm, and one outcome.
class ScanScreen extends ConsumerStatefulWidget {
  /// Creates the scanner for the selected [convention].
  const new({
    required this.convention,
    required this.onOpenRequests,
    required this.onOpenCatches,
    required this.onReloadHome,
    required this.onClose,
    super.key,
  });

  /// The selected convention of the home.
  final Convention convention;

  /// Closes the scanner and opens the request list.
  final VoidCallback onOpenRequests;

  /// Closes the scanner and opens the collection.
  final VoidCallback onOpenCatches;

  /// Reads the home state again.
  final VoidCallback onReloadHome;

  /// Closes the scanner and shows the home.
  final VoidCallback onClose;

  @override
  ConsumerState<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends ConsumerState<ScanScreen>
    with WidgetsBindingObserver {
  /// Null while the status read runs.
  CameraAccess? _access;
  QrScanner? _scanner;
  bool _scannerFailed = false;
  bool _torchOn = false;

  CameraPermission get _permission => ref.read(cameraPermissionProvider);

  /// The convention that the scanner opened for. A home reload after a
  /// convention change must not swap the scan, or the change message would
  /// vanish and a new scan could start at a closed convention (#511 AC13).
  late final Convention _convention = widget.convention;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_readAccess());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_scanner?.dispose());
    _scanner = null;
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final scanner = _scanner;
    switch (state) {
      case AppLifecycleState.resumed:
        if (_access == CameraAccess.granted) {
          // MobileScanner follows the lifecycle only for a controller that
          // it owns, so the screen starts the camera again (#511 AC9).
          if (scanner != null) {
            unawaited(_guard(scanner.start));
          }
        } else {
          // The player can change the permission in Settings and come back.
          unawaited(_readAccess());
        }
      case AppLifecycleState.inactive ||
          AppLifecycleState.hidden ||
          AppLifecycleState.paused:
        if (scanner != null) {
          unawaited(_guard(scanner.stop));
          // The camera stop turns the flashlight off.
          if (_torchOn) {
            setState(() => _torchOn = false);
          }
        }
      case AppLifecycleState.detached:
        return;
    }
  }

  /// Runs a camera call. A failure shows the scanner banner and is never
  /// logged, because a camera error can hold scanned text.
  Future<void> _guard(Future<void> Function() call) async {
    try {
      await call();
    } on Object {
      _onScannerError();
    }
  }

  Future<void> _readAccess() async {
    final access = await _permission.status();
    if (mounted) {
      setState(() => _access = access);
    }
  }

  Future<void> _turnOnCamera() async {
    final access = await _permission.request();
    if (mounted) {
      setState(() => _access = access);
    }
  }

  /// The camera session of the current scan. A new scan gets a new session,
  /// so the same tag can be read again.
  QrScanner _session() =>
      _scanner ??= ref.read(qrScannerFactoryProvider).call();

  void _endSession() {
    final scanner = _scanner;
    _scanner = null;
    _torchOn = false;
    if (scanner != null) {
      unawaited(scanner.dispose());
    }
  }

  void _restartScanner() {
    _endSession();
    setState(() => _scannerFailed = false);
  }

  void _onCode(String raw) {
    final controller = ref.read(
      scanControllerProvider(_convention.id).notifier,
    );
    if (controller.read(raw)) {
      unawaited(HapticFeedback.mediumImpact());
      unawaited(
        SemanticsService.sendAnnouncement(
          View.of(context),
          CatchStrings.tagFound,
          Directionality.of(context),
        ),
      );
    }
  }

  void _onScannerError() {
    if (mounted && !_scannerFailed) {
      _endSession();
      setState(() => _scannerFailed = true);
    }
  }

  Future<void> _toggleTorch() async {
    final scanner = _scanner;
    if (scanner == null) {
      return;
    }
    await scanner.toggleTorch();
    if (mounted) {
      setState(() => _torchOn = !_torchOn);
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = scanControllerProvider(_convention.id);
    ref.listen(provider, (previous, next) {
      if (next.phase != ScanPhase.scanning) {
        _endSession();
      }
      final result = next.result;
      if (result == previous?.result) {
        return;
      }
      if (reloadHomeResults.contains(result)) {
        widget.onReloadHome();
      }
      // A catch changes the collection, and a request changes the request
      // list, so a live section reads again (#511 AC25, AC29). A section
      // that is not alive reads when it opens.
      if (result == ScanResult.approved || result == ScanResult.alreadyCaught) {
        final catches = catchesControllerProvider(_convention.id);
        if (ref.read(catches.exists)) {
          unawaited(ref.read(catches.notifier).read());
        }
      }
      if (result == ScanResult.pending ||
          result == ScanResult.alreadyPending ||
          result == ScanResult.approved) {
        if (ref.read(requestsControllerProvider.exists)) {
          unawaited(ref.read(requestsControllerProvider.notifier).read());
        }
      }
    });
    final state = ref.watch(provider);
    final controller = ref.read(provider.notifier);
    return Scaffold(
      appBar: AppBar(
        title: const Text(CatchStrings.scanTag),
        actions: [
          if (state.phase == ScanPhase.scanning &&
              _access == CameraAccess.granted &&
              !_scannerFailed)
            IconButton(
              key: const Key("scan-torch"),
              tooltip: _torchOn ? CatchStrings.torchOff : CatchStrings.torchOn,
              icon: Icon(_torchOn ? Icons.flashlight_off : Icons.flashlight_on),
              onPressed: _toggleTorch,
            ),
        ],
      ),
      body: SafeArea(
        child: switch (state.phase) {
          ScanPhase.scanning => _camera(state),
          ScanPhase.previewing => const _Loading(),
          ScanPhase.preview || ScanPhase.submitting => _PreviewView(
            state: state,
            conventionName: _convention.name,
            onConfirm: controller.confirm,
            onScanAgain: controller.scanAgain,
          ),
          ScanPhase.result => _ResultView(
            state: state,
            convention: _convention,
            onRetry: controller.retry,
            onScanAgain: controller.scanAgain,
            onOpenRequests: widget.onOpenRequests,
            onOpenCatches: widget.onOpenCatches,
            onClose: widget.onClose,
          ),
        },
      ),
    );
  }

  Widget _camera(ScanState state) {
    return switch (_access) {
      null => const _Loading(),
      CameraAccess.undecided => _CameraMessage(
        key: const Key("scan-camera-intro"),
        message: CatchStrings.cameraIntro,
        action: TailTagButton(
          key: const Key("scan-turn-on-camera"),
          label: CatchStrings.turnOnCamera,
          onPressed: _turnOnCamera,
        ),
      ),
      CameraAccess.denied => _CameraMessage(
        key: const Key("scan-camera-denied"),
        message: CatchStrings.cameraDenied,
        action: TailTagButton(
          key: const Key("scan-open-settings"),
          label: CatchStrings.openSettings,
          onPressed: () => unawaited(_permission.openSettings()),
        ),
      ),
      CameraAccess.granted => _liveCamera(state),
    };
  }

  Widget _liveCamera(ScanState state) {
    return Padding(
      padding: const EdgeInsets.all(TokenSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: TokenSpacing.lg,
        children: [
          const Text(CatchStrings.pointCamera),
          if (_scannerFailed)
            StatusBanner(
              key: const Key("scan-banner"),
              tone: StatusTone.warning,
              message: CatchStrings.scannerNotReady,
              actionLabel: UiStrings.tryAgain,
              onAction: _restartScanner,
            )
          else if (state.notATag)
            const StatusBanner(
              key: Key("scan-banner"),
              tone: StatusTone.warning,
              message: CatchStrings.notATag,
            ),
          if (!_scannerFailed)
            Expanded(
              child: Semantics(
                key: const Key("scan-viewfinder"),
                label: CatchStrings.viewfinderLabel,
                image: true,
                child: ExcludeSemantics(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(TokenRadius.large),
                    child: _session().buildView(
                      onCode: _onCode,
                      onError: _onScannerError,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const DelayedVisibility(
      child: Center(
        child: CircularProgressIndicator(semanticsLabel: UiStrings.loading),
      ),
    );
  }
}

class _CameraMessage extends StatelessWidget {
  const new({required this.message, required this.action, super.key});

  final String message;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(TokenSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: TokenSpacing.lg,
        children: [
          Text(message, style: Theme.of(context).textTheme.bodyLarge),
          action,
        ],
      ),
    );
  }
}

/// The suit card with the confirm button.
class _PreviewView extends StatelessWidget {
  const new({
    required this.state,
    required this.conventionName,
    required this.onConfirm,
    required this.onScanAgain,
  });

  final ScanState state;
  final String conventionName;
  final VoidCallback onConfirm;
  final VoidCallback onScanAgain;

  @override
  Widget build(BuildContext context) {
    final preview = state.preview;
    if (preview == null) {
      return const _Loading();
    }
    final textTheme = Theme.of(context).textTheme;
    final name = preview.fursuit.name;
    final submitting = state.phase == ScanPhase.submitting;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(TokenSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: TokenSpacing.lg,
        children: [
          Card(
            key: const Key("scan-preview"),
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(TokenSpacing.lg),
              child: Column(
                spacing: TokenSpacing.md,
                children: [
                  TailTagAvatar(
                    name: name,
                    kind: AvatarKind.fursuit,
                    imageUrl: preview.fursuit.photoUrl.toString(),
                    size: AvatarSize.photo,
                  ),
                  Text(
                    name,
                    textAlign: TextAlign.center,
                    style: textTheme.titleLarge,
                  ),
                  Text(
                    conventionName,
                    textAlign: TextAlign.center,
                    style: textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ),
          TailTagButton(
            key: const Key("scan-confirm"),
            label: CatchStrings.catchSuit(name),
            loading: submitting,
            onPressed: onConfirm,
          ),
          TailTagButton(
            key: const Key("scan-again"),
            label: CatchStrings.scanAgain,
            variant: TailTagButtonVariant.secondary,
            onPressed: submitting ? null : onScanAgain,
          ),
        ],
      ),
    );
  }
}

/// The outcome text. A refusal or a failure is a status banner. A success
/// or a neutral outcome is the screen's main content, so it is a card: the
/// status banner is never a success message.
class _Outcome extends StatelessWidget {
  const new({required this.tone, required this.message});

  final StatusTone tone;
  final String message;

  @override
  Widget build(BuildContext context) {
    if (tone == StatusTone.warning || tone == StatusTone.error) {
      return StatusBanner(
        key: const Key("scan-result"),
        tone: tone,
        message: message,
      );
    }
    return Card(
      key: const Key("scan-result"),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(TokenSpacing.lg),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: TokenSpacing.md,
          children: [
            ExcludeSemantics(child: Icon(context.statusStyle(tone).icon)),
            Expanded(
              child: Text(
                message,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// One outcome and its buttons (#511 AC15 to AC19).
class _ResultView extends StatelessWidget {
  const new({
    required this.state,
    required this.convention,
    required this.onRetry,
    required this.onScanAgain,
    required this.onOpenRequests,
    required this.onOpenCatches,
    required this.onClose,
  });

  final ScanState state;
  final Convention convention;
  final VoidCallback onRetry;
  final VoidCallback onScanAgain;
  final VoidCallback onOpenRequests;
  final VoidCallback onOpenCatches;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final result = state.result ?? ScanResult.failed;
    final name = state.preview?.fursuit.name ?? "";
    final (tone, message) = switch (result) {
      ScanResult.pending => (
        StatusTone.success,
        CatchStrings.sent(name, _deadline(context)),
      ),
      ScanResult.approved => (StatusTone.success, CatchStrings.caught(name)),
      ScanResult.alreadyPending => (
        StatusTone.neutral,
        CatchStrings.alreadyPending(name),
      ),
      ScanResult.alreadyCaught => (
        StatusTone.neutral,
        CatchStrings.alreadyCaught(name),
      ),
      ScanResult.unavailable => (StatusTone.warning, CatchStrings.unavailable),
      ScanResult.ownSuit => (StatusTone.warning, CatchStrings.ownSuit),
      ScanResult.ineligible => (StatusTone.warning, CatchStrings.ineligible),
      ScanResult.closed => (
        StatusTone.warning,
        CatchStrings.closed(convention.name),
      ),
      ScanResult.wait => (
        StatusTone.warning,
        CatchStrings.wait(state.waitSeconds),
      ),
      ScanResult.unknown => (StatusTone.warning, CatchStrings.unknown),
      ScanResult.serviceOff => (StatusTone.warning, CatchStrings.serviceOff),
      ScanResult.conventionChanged => (
        StatusTone.warning,
        CatchStrings.conventionChanged,
      ),
      ScanResult.failed => (
        StatusTone.error,
        (switch (state.failure) {
                  null => null,
                  final failure => genericErrorFor(failure),
                } ??
                GenericError.unknown)
            .message,
      ),
    };
    final primary = switch (result) {
      ScanResult.pending || ScanResult.alreadyPending => TailTagButton(
        key: const Key("scan-see-requests"),
        label: CatchStrings.seeRequests,
        onPressed: onOpenRequests,
      ),
      ScanResult.approved || ScanResult.alreadyCaught => TailTagButton(
        key: const Key("scan-see-catches"),
        label: CatchStrings.seeCatches,
        onPressed: onOpenCatches,
      ),
      ScanResult.unknown => TailTagButton(
        key: const Key("scan-retry"),
        label: CatchStrings.checkAgain,
        onPressed: onRetry,
      ),
      ScanResult.wait || ScanResult.failed => TailTagButton(
        key: const Key("scan-retry"),
        label: UiStrings.tryAgain,
        onPressed: state.waitSeconds > 0 ? null : onRetry,
      ),
      _ => null,
    };
    return SingleChildScrollView(
      padding: const EdgeInsets.all(TokenSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: TokenSpacing.lg,
        children: [
          // A live region, so a screen reader reads each new outcome and
          // each countdown step.
          Semantics(
            liveRegion: true,
            child: _Outcome(tone: tone, message: message),
          ),
          ?primary,
          // After a convention change the scan belongs to the old
          // convention, so the only way on is the updated home.
          if (result == ScanResult.conventionChanged)
            TailTagButton(
              key: const Key("scan-close"),
              label: CatchStrings.backToHome,
              onPressed: onClose,
            )
          else
            TailTagButton(
              key: const Key("scan-again"),
              label: CatchStrings.scanAgain,
              variant: primary == null
                  ? TailTagButtonVariant.primary
                  : TailTagButtonVariant.secondary,
              onPressed: onScanAgain,
            ),
        ],
      ),
    );
  }

  String _deadline(BuildContext context) {
    final request = state.request;
    final deadline = request?.reviewDeadlineAt ?? convention.reviewDeadlineAt;
    if (deadline == null) {
      return "";
    }
    return CatchStrings.reviewEnd(
      context,
      convention: request == null || request.conventionId == convention.id
          ? convention
          : null,
      deadlineAt: deadline,
    );
  }
}
