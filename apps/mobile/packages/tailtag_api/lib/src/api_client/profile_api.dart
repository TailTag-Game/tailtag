// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i7;

import 'package:http/http.dart' as _i10;
import 'package:tailtag_api/src/model/avatar_put.dart' as _i16;
import 'package:tailtag_api/src/operation/profile_avatar_destroy.dart' as _i6;
import 'package:tailtag_api/src/operation/profile_avatar_update.dart' as _i5;
import 'package:tailtag_api/src/operation/profile_partial_update.dart' as _i4;
import 'package:tailtag_api/src/operation/profile_retrieve.dart' as _i2;
import 'package:tailtag_api/src/operation/profile_update.dart' as _i3;
import 'package:tailtag_api/src/request_body/api_profile_patch_body_request_body.dart'
    as _i14;
import 'package:tailtag_api/src/request_body/api_profile_put_body_request_body.dart'
    as _i12;
import 'package:tailtag_api/src/response_wrapper/profile_avatar_destroy_response.dart'
    as _i17;
import 'package:tailtag_api/src/response_wrapper/profile_avatar_update_response.dart'
    as _i15;
import 'package:tailtag_api/src/response_wrapper/profile_partial_update_response.dart'
    as _i13;
import 'package:tailtag_api/src/response_wrapper/profile_retrieve_response.dart'
    as _i9;
import 'package:tailtag_api/src/response_wrapper/profile_update_response.dart'
    as _i11;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i8;

class ProfileApi {
  ProfileApi(_i1.Server server)
    : _profileRetrieve = _i2.ProfileRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _profileUpdate = _i3.ProfileUpdate(server.baseUrl, () => server.client),
      _profilePartialUpdate = _i4.ProfilePartialUpdate(
        server.baseUrl,
        () => server.client,
      ),
      _profileAvatarUpdate = _i5.ProfileAvatarUpdate(
        server.baseUrl,
        () => server.client,
      ),
      _profileAvatarDestroy = _i6.ProfileAvatarDestroy(
        server.baseUrl,
        () => server.client,
      );

  final _i2.ProfileRetrieve _profileRetrieve;

  final _i3.ProfileUpdate _profileUpdate;

  final _i4.ProfilePartialUpdate _profilePartialUpdate;

  final _i5.ProfileAvatarUpdate _profileAvatarUpdate;

  final _i6.ProfileAvatarDestroy _profileAvatarDestroy;

  /// Read or mutate the authenticated user's private player profile.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i9.ProfileRetrieveResponse, _i10.Response>>
  profileRetrieve({_i8.TonikCancellation? cancellation}) async =>
      _profileRetrieve(cancellation: cancellation);

  /// Completely replace handle and display_name while preserving the independently managed avatar state.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i11.ProfileUpdateResponse, _i10.Response>>
  profileUpdate({
    required _i12.ApiProfilePutBodyRequestBody body,
    _i8.TonikCancellation? cancellation,
  }) async => _profileUpdate(body: body, cancellation: cancellation);

  /// Read or mutate the authenticated user's private player profile.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i13.ProfilePartialUpdateResponse, _i10.Response>>
  profilePartialUpdate({
    _i14.ApiProfilePatchBodyRequestBody? body,
    _i8.TonikCancellation? cancellation,
  }) async => _profilePartialUpdate(body: body, cancellation: cancellation);

  /// Replace the independently managed avatar using multipart/form-data.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i15.ProfileAvatarUpdateResponse, _i10.Response>>
  profileAvatarUpdate({
    required _i16.AvatarPut body,
    _i8.TonikCancellation? cancellation,
  }) async => _profileAvatarUpdate(body: body, cancellation: cancellation);

  /// Mutate the authenticated user's independently managed avatar.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i17.ProfileAvatarDestroyResponse, _i10.Response>>
  profileAvatarDestroy({_i8.TonikCancellation? cancellation}) async =>
      _profileAvatarDestroy(cancellation: cancellation);
}
