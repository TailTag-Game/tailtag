// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i7;

import 'package:http/http.dart' as _i10;
import 'package:tailtag_api/src/model/api_fursuits_id_patch_body_body_model.dart'
    as _i15;
import 'package:tailtag_api/src/model/api_fursuits_id_photo_put_body_body_model.dart'
    as _i17;
import 'package:tailtag_api/src/model/api_fursuits_post_body_body_model.dart'
    as _i12;
import 'package:tailtag_api/src/operation/fursuits_create.dart' as _i3;
import 'package:tailtag_api/src/operation/fursuits_list.dart' as _i2;
import 'package:tailtag_api/src/operation/fursuits_replace_photo.dart' as _i6;
import 'package:tailtag_api/src/operation/fursuits_retrieve.dart' as _i4;
import 'package:tailtag_api/src/operation/fursuits_update_name.dart' as _i5;
import 'package:tailtag_api/src/response_wrapper/fursuits_create_response.dart'
    as _i11;
import 'package:tailtag_api/src/response_wrapper/fursuits_list_response.dart'
    as _i9;
import 'package:tailtag_api/src/response_wrapper/fursuits_replace_photo_response.dart'
    as _i16;
import 'package:tailtag_api/src/response_wrapper/fursuits_retrieve_response.dart'
    as _i13;
import 'package:tailtag_api/src/response_wrapper/fursuits_update_name_response.dart'
    as _i14;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i8;

class FursuitsApi {
  FursuitsApi(_i1.Server server)
    : _fursuitsList = _i2.FursuitsList(server.baseUrl, () => server.client),
      _fursuitsCreate = _i3.FursuitsCreate(server.baseUrl, () => server.client),
      _fursuitsRetrieve = _i4.FursuitsRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _fursuitsUpdateName = _i5.FursuitsUpdateName(
        server.baseUrl,
        () => server.client,
      ),
      _fursuitsReplacePhoto = _i6.FursuitsReplacePhoto(
        server.baseUrl,
        () => server.client,
      );

  final _i2.FursuitsList _fursuitsList;

  final _i3.FursuitsCreate _fursuitsCreate;

  final _i4.FursuitsRetrieve _fursuitsRetrieve;

  final _i5.FursuitsUpdateName _fursuitsUpdateName;

  final _i6.FursuitsReplacePhoto _fursuitsReplacePhoto;

  /// List owned records or create one required-photo record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i9.FursuitsListResponse, _i10.Response>>
  fursuitsList({_i8.TonikCancellation? cancellation}) async =>
      _fursuitsList(cancellation: cancellation);

  /// List owned records or create one required-photo record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i11.FursuitsCreateResponse, _i10.Response>>
  fursuitsCreate({
    _i12.ApiFursuitsPostBodyBodyModel? body,
    _i8.TonikCancellation? cancellation,
  }) async => _fursuitsCreate(body: body, cancellation: cancellation);

  /// Retrieve or rename a private player record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i13.FursuitsRetrieveResponse, _i10.Response>>
  fursuitsRetrieve({
    required _i7.int id,
    _i8.TonikCancellation? cancellation,
  }) async => _fursuitsRetrieve(id: id, cancellation: cancellation);

  /// Retrieve or rename a private player record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i14.FursuitsUpdateNameResponse, _i10.Response>>
  fursuitsUpdateName({
    required _i7.int id,
    _i15.ApiFursuitsIdPatchBodyBodyModel? body,
    _i8.TonikCancellation? cancellation,
  }) async =>
      _fursuitsUpdateName(body: body, id: id, cancellation: cancellation);

  /// Replace the required photo of a private player record.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i16.FursuitsReplacePhotoResponse, _i10.Response>>
  fursuitsReplacePhoto({
    required _i7.int id,
    _i17.ApiFursuitsIdPhotoPutBodyBodyModel? body,
    _i8.TonikCancellation? cancellation,
  }) async =>
      _fursuitsReplacePhoto(body: body, id: id, cancellation: cancellation);
}
