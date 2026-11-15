import "package:flutter/services.dart";
import "package:image_picker/image_picker.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";

/// Where a photo comes from.
enum PhotoOrigin {
  /// The device photo library.
  library,

  /// The device camera.
  camera,
}

/// The device refused access to the camera or the photo library.
final class PhotoAccessDenied implements Exception {
  /// Creates the failure for [origin].
  const new(this.origin);

  /// The origin that the device refused.
  final PhotoOrigin origin;
}

/// The picker could not deliver a photo for another reason.
final class PhotoPickFailed implements Exception {
  /// Creates the failure.
  const new();
}

/// The seam between the app and the device photo picker.
abstract interface class PhotoSource {
  /// Lets the owner pick one photo from [origin]. It returns null when the
  /// owner cancels. It throws [PhotoAccessDenied] or [PhotoPickFailed].
  Future<PickedPhoto?> pick(PhotoOrigin origin);
}

/// The longest side, in pixels, of a picked photo. The server accepts up to
/// 25 megapixels and 10 MB, so the picker scales and re-encodes large
/// photos below both limits.
const double maxPhotoSide = 2048;

/// The re-encode quality of a picked photo.
const int photoQuality = 85;

/// [PhotoSource] over the `image_picker` plugin.
final class ImagePickerPhotoSource implements PhotoSource {
  /// Creates the source.
  const new();

  @override
  Future<PickedPhoto?> pick(PhotoOrigin origin) async {
    final XFile? file;
    try {
      file = await ImagePicker().pickImage(
        source: switch (origin) {
          PhotoOrigin.library => ImageSource.gallery,
          PhotoOrigin.camera => ImageSource.camera,
        },
        maxWidth: maxPhotoSide,
        maxHeight: maxPhotoSide,
        imageQuality: photoQuality,
        requestFullMetadata: false,
      );
    } on PlatformException catch (error) {
      if (error.code == "camera_access_denied" ||
          error.code == "photo_access_denied") {
        throw PhotoAccessDenied(origin);
      }
      throw const PhotoPickFailed();
    }
    if (file == null) {
      return null;
    }
    return PickedPhoto(bytes: await file.readAsBytes(), name: file.name);
  }
}
