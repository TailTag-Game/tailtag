import "package:flutter/material.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/photo_source.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";

/// What the photo choice produced.
sealed class PhotoPickOutcome {
  const new();
}

/// The owner picked [photo].
final class PhotoPicked extends PhotoPickOutcome {
  /// Creates the outcome.
  const new(this.photo);

  /// The picked photo.
  final PickedPhoto photo;
}

/// The owner closed the sheet or the picker.
final class PhotoPickCancelled extends PhotoPickOutcome {
  /// Creates the outcome.
  const new();
}

/// The device refused access, or the picker failed. [message] says why.
final class PhotoPickProblem extends PhotoPickOutcome {
  /// Creates the outcome.
  const new(this.message);

  /// The text to show.
  final String message;
}

/// Shows the photo choice sheet, then the device picker.
Future<PhotoPickOutcome> pickSuitPhoto(
  BuildContext context,
  PhotoSource source,
) async {
  final origin = await showModalBottomSheet<PhotoOrigin>(
    context: context,
    showDragHandle: true,
    useSafeArea: true,
    builder: (context) => const _PhotoChoiceSheet(),
  );
  if (origin == null) {
    return const PhotoPickCancelled();
  }
  try {
    final photo = await source.pick(origin);
    return photo == null ? const PhotoPickCancelled() : PhotoPicked(photo);
  } on PhotoAccessDenied catch (denied) {
    return PhotoPickProblem(switch (denied.origin) {
      PhotoOrigin.camera => FursuitStrings.cameraDenied,
      PhotoOrigin.library => FursuitStrings.libraryDenied,
    });
  } on PhotoPickFailed {
    return const PhotoPickProblem(FursuitStrings.pickFailed);
  }
}

class _PhotoChoiceSheet extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        TokenSpacing.sm,
        0,
        TokenSpacing.sm,
        TokenSpacing.lg,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            key: const Key("photo-choose"),
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text(FursuitStrings.choosePhoto),
            onTap: () => Navigator.of(context).pop(PhotoOrigin.library),
          ),
          ListTile(
            key: const Key("photo-take"),
            leading: const Icon(Icons.photo_camera_outlined),
            title: const Text(FursuitStrings.takePhoto),
            onTap: () => Navigator.of(context).pop(PhotoOrigin.camera),
          ),
        ],
      ),
    );
  }
}
