// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i9;

import 'package:http/http.dart' as _i12;
import 'package:tailtag_api/src/model/api_fursuits_id_patch_body_body_model.dart'
    as _i17;
import 'package:tailtag_api/src/model/api_fursuits_id_photo_put_body_body_model.dart'
    as _i19;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post_body_body_model.dart'
    as _i22;
import 'package:tailtag_api/src/model/api_fursuits_post_body_body_model.dart'
    as _i14;
import 'package:tailtag_api/src/operation/fursuit_tag_replace.dart' as _i8;
import 'package:tailtag_api/src/operation/fursuit_tag_retrieve.dart' as _i7;
import 'package:tailtag_api/src/operation/fursuits_create.dart' as _i3;
import 'package:tailtag_api/src/operation/fursuits_list.dart' as _i2;
import 'package:tailtag_api/src/operation/fursuits_replace_photo.dart' as _i6;
import 'package:tailtag_api/src/operation/fursuits_retrieve.dart' as _i4;
import 'package:tailtag_api/src/operation/fursuits_update.dart' as _i5;
import 'package:tailtag_api/src/response_wrapper/fursuit_tag_replace_response.dart'
    as _i21;
import 'package:tailtag_api/src/response_wrapper/fursuit_tag_retrieve_response.dart'
    as _i20;
import 'package:tailtag_api/src/response_wrapper/fursuits_create_response.dart'
    as _i13;
import 'package:tailtag_api/src/response_wrapper/fursuits_list_response.dart'
    as _i11;
import 'package:tailtag_api/src/response_wrapper/fursuits_replace_photo_response.dart'
    as _i18;
import 'package:tailtag_api/src/response_wrapper/fursuits_retrieve_response.dart'
    as _i15;
import 'package:tailtag_api/src/response_wrapper/fursuits_update_response.dart'
    as _i16;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i10;

class FursuitsApi {
  FursuitsApi(_i1.Server server)
    : _fursuitsList = _i2.FursuitsList(server.baseUrl, () => server.client),
      _fursuitsCreate = _i3.FursuitsCreate(server.baseUrl, () => server.client),
      _fursuitsRetrieve = _i4.FursuitsRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _fursuitsUpdate = _i5.FursuitsUpdate(server.baseUrl, () => server.client),
      _fursuitsReplacePhoto = _i6.FursuitsReplacePhoto(
        server.baseUrl,
        () => server.client,
      ),
      _fursuitTagRetrieve = _i7.FursuitTagRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _fursuitTagReplace = _i8.FursuitTagReplace(
        server.baseUrl,
        () => server.client,
      );

  final _i2.FursuitsList _fursuitsList;

  final _i3.FursuitsCreate _fursuitsCreate;

  final _i4.FursuitsRetrieve _fursuitsRetrieve;

  final _i5.FursuitsUpdate _fursuitsUpdate;

  final _i6.FursuitsReplacePhoto _fursuitsReplacePhoto;

  final _i7.FursuitTagRetrieve _fursuitTagRetrieve;

  final _i8.FursuitTagReplace _fursuitTagReplace;

  /// List owned records or create one required-photo record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i11.FursuitsListResponse, _i12.Response>>
  fursuitsList({_i10.TonikCancellation? cancellation}) async =>
      _fursuitsList(cancellation: cancellation);

  /// List owned records or create one required-photo record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i13.FursuitsCreateResponse, _i12.Response>>
  fursuitsCreate({
    _i14.ApiFursuitsPostBodyBodyModel? body,
    _i10.TonikCancellation? cancellation,
  }) async => _fursuitsCreate(body: body, cancellation: cancellation);

  /// Retrieve a private player record, or change its name or approval mode.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i15.FursuitsRetrieveResponse, _i12.Response>>
  fursuitsRetrieve({
    required _i9.int id,
    _i10.TonikCancellation? cancellation,
  }) async => _fursuitsRetrieve(id: id, cancellation: cancellation);

  /// Retrieve a private player record, or change its name or approval mode.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i16.FursuitsUpdateResponse, _i12.Response>>
  fursuitsUpdate({
    required _i17.ApiFursuitsIdPatchBodyBodyModel body,
    required _i9.int id,
    _i10.TonikCancellation? cancellation,
  }) async => _fursuitsUpdate(body: body, id: id, cancellation: cancellation);

  /// Replace the required photo of a private player record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i18.FursuitsReplacePhotoResponse, _i12.Response>>
  fursuitsReplacePhoto({
    required _i9.int id,
    _i19.ApiFursuitsIdPhotoPutBodyBodyModel? body,
    _i10.TonikCancellation? cancellation,
  }) async =>
      _fursuitsReplacePhoto(body: body, id: id, cancellation: cancellation);

  /// Return the current reusable tag for an owned suit. The first read creates the first tag. After an operator revocation, the read returns state revoked and no payload, and never creates a replacement.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i20.FursuitTagRetrieveResponse, _i12.Response>>
  fursuitTagRetrieve({
    required _i9.int id,
    _i10.TonikCancellation? cancellation,
  }) async => _fursuitTagRetrieve(id: id, cancellation: cancellation);

  /// Replace the tag when expected_version matches the current tag_version. Old copies stop working. A stale version returns tag_version_conflict and changes nothing. After a lost response, read the tag again and never replace again automatically.
  ///
  /// Security:
  /// - HTTP Bearer
  _i9.Future<_i10.TonikResult<_i21.FursuitTagReplaceResponse, _i12.Response>>
  fursuitTagReplace({
    required _i22.ApiFursuitsIdTagReplacePostBodyBodyModel body,
    required _i9.int id,
    _i10.TonikCancellation? cancellation,
  }) async =>
      _fursuitTagReplace(body: body, id: id, cancellation: cancellation);
}
