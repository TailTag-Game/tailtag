// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i15;

import 'package:http/http.dart' as _i18;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post_body_body_model.dart'
    as _i20;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_session_put_body_body_model.dart'
    as _i27;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put_body_body_model.dart'
    as _i23;
import 'package:tailtag_api/src/operation/convention_fursuit_activations_list.dart'
    as _i4;
import 'package:tailtag_api/src/operation/convention_fursuit_activations_set_state.dart'
    as _i5;
import 'package:tailtag_api/src/operation/convention_fursuit_catch_credential_get.dart'
    as _i6;
import 'package:tailtag_api/src/operation/convention_fursuit_catch_credential_resolve.dart'
    as _i3;
import 'package:tailtag_api/src/operation/convention_fursuit_catch_credential_rotate.dart'
    as _i7;
import 'package:tailtag_api/src/operation/convention_fursuit_catch_session_set_state.dart'
    as _i8;
import 'package:tailtag_api/src/operation/conventions_active_destroy.dart'
    as _i12;
import 'package:tailtag_api/src/operation/conventions_active_retrieve.dart'
    as _i10;
import 'package:tailtag_api/src/operation/conventions_active_update.dart'
    as _i11;
import 'package:tailtag_api/src/operation/conventions_enrollments_create.dart'
    as _i14;
import 'package:tailtag_api/src/operation/conventions_enrollments_list.dart'
    as _i13;
import 'package:tailtag_api/src/operation/conventions_list.dart' as _i2;
import 'package:tailtag_api/src/operation/conventions_retrieve.dart' as _i9;
import 'package:tailtag_api/src/request_body/api_conventions_active_put_body_request_body.dart'
    as _i31;
import 'package:tailtag_api/src/request_body/api_conventions_enrollments_post_body_request_body.dart'
    as _i35;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_activations_list_response.dart'
    as _i21;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_activations_set_state_response.dart'
    as _i22;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_get_response.dart'
    as _i24;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_resolve_response.dart'
    as _i19;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_rotate_response.dart'
    as _i25;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_session_set_state_response.dart'
    as _i26;
import 'package:tailtag_api/src/response_wrapper/conventions_active_destroy_response.dart'
    as _i32;
import 'package:tailtag_api/src/response_wrapper/conventions_active_retrieve_response.dart'
    as _i29;
import 'package:tailtag_api/src/response_wrapper/conventions_active_update_response.dart'
    as _i30;
import 'package:tailtag_api/src/response_wrapper/conventions_enrollments_create_response.dart'
    as _i34;
import 'package:tailtag_api/src/response_wrapper/conventions_enrollments_list_response.dart'
    as _i33;
import 'package:tailtag_api/src/response_wrapper/conventions_list_response.dart'
    as _i17;
import 'package:tailtag_api/src/response_wrapper/conventions_retrieve_response.dart'
    as _i28;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i16;

class ConventionsApi {
  ConventionsApi(_i1.Server server)
    : _conventionsList = _i2.ConventionsList(
        server.baseUrl,
        () => server.client,
      ),
      _conventionFursuitCatchCredentialResolve =
          _i3.ConventionFursuitCatchCredentialResolve(
            server.baseUrl,
            () => server.client,
          ),
      _conventionFursuitActivationsList = _i4.ConventionFursuitActivationsList(
        server.baseUrl,
        () => server.client,
      ),
      _conventionFursuitActivationsSetState =
          _i5.ConventionFursuitActivationsSetState(
            server.baseUrl,
            () => server.client,
          ),
      _conventionFursuitCatchCredentialGet =
          _i6.ConventionFursuitCatchCredentialGet(
            server.baseUrl,
            () => server.client,
          ),
      _conventionFursuitCatchCredentialRotate =
          _i7.ConventionFursuitCatchCredentialRotate(
            server.baseUrl,
            () => server.client,
          ),
      _conventionFursuitCatchSessionSetState =
          _i8.ConventionFursuitCatchSessionSetState(
            server.baseUrl,
            () => server.client,
          ),
      _conventionsRetrieve = _i9.ConventionsRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _conventionsActiveRetrieve = _i10.ConventionsActiveRetrieve(
        server.baseUrl,
        () => server.client,
      ),
      _conventionsActiveUpdate = _i11.ConventionsActiveUpdate(
        server.baseUrl,
        () => server.client,
      ),
      _conventionsActiveDestroy = _i12.ConventionsActiveDestroy(
        server.baseUrl,
        () => server.client,
      ),
      _conventionsEnrollmentsList = _i13.ConventionsEnrollmentsList(
        server.baseUrl,
        () => server.client,
      ),
      _conventionsEnrollmentsCreate = _i14.ConventionsEnrollmentsCreate(
        server.baseUrl,
        () => server.client,
      );

  final _i2.ConventionsList _conventionsList;

  final _i3.ConventionFursuitCatchCredentialResolve
  _conventionFursuitCatchCredentialResolve;

  final _i4.ConventionFursuitActivationsList _conventionFursuitActivationsList;

  final _i5.ConventionFursuitActivationsSetState
  _conventionFursuitActivationsSetState;

  final _i6.ConventionFursuitCatchCredentialGet
  _conventionFursuitCatchCredentialGet;

  final _i7.ConventionFursuitCatchCredentialRotate
  _conventionFursuitCatchCredentialRotate;

  final _i8.ConventionFursuitCatchSessionSetState
  _conventionFursuitCatchSessionSetState;

  final _i9.ConventionsRetrieve _conventionsRetrieve;

  final _i10.ConventionsActiveRetrieve _conventionsActiveRetrieve;

  final _i11.ConventionsActiveUpdate _conventionsActiveUpdate;

  final _i12.ConventionsActiveDestroy _conventionsActiveDestroy;

  final _i13.ConventionsEnrollmentsList _conventionsEnrollmentsList;

  final _i14.ConventionsEnrollmentsCreate _conventionsEnrollmentsCreate;

  /// List conventions
  /// Retrieve a list of conventions with safe public fields for enrollment.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i17.ConventionsListResponse, _i18.Response>>
  conventionsList({_i16.TonikCancellation? cancellation}) async =>
      _conventionsList(cancellation: cancellation);

  /// Resolve an opaque catch credential to a safe current preview only. This is not catch authorization; future Wave 3 catch writes must submit and independently revalidate the original payload.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i19.ConventionFursuitCatchCredentialResolveResponse,
      _i18.Response
    >
  >
  conventionFursuitCatchCredentialResolve({
    required _i15.int conventionId,
    _i20.ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel?
    body,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitCatchCredentialResolve(
    body: body,
    conventionId: conventionId,
    cancellation: cancellation,
  );

  /// Return existing owner selections in ascending fursuit_id order. is_active is the stored selection; is_eligible is computed from current upstream state. Operational participation requires both.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i21.ConventionFursuitActivationsListResponse,
      _i18.Response
    >
  >
  conventionFursuitActivationsList({
    required _i15.int conventionId,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitActivationsList(
    conventionId: conventionId,
    cancellation: cancellation,
  );

  /// Idempotently set the stored is_active owner selection. is_eligible is computed from current upstream state; operational participation requires both the stored selection and computed eligibility.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i22.ConventionFursuitActivationsSetStateResponse,
      _i18.Response
    >
  >
  conventionFursuitActivationsSetState({
    required _i15.int conventionId,
    required _i15.int fursuitId,
    _i23.ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel?
    body,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitActivationsSetState(
    body: body,
    conventionId: conventionId,
    fursuitId: fursuitId,
    cancellation: cancellation,
  );

  /// Return the owner's current opaque catch credential, creating it lazily when absent. This does not start a catch session and is not catch authorization.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i24.ConventionFursuitCatchCredentialGetResponse,
      _i18.Response
    >
  >
  conventionFursuitCatchCredentialGet({
    required _i15.int conventionId,
    required _i15.int fursuitId,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitCatchCredentialGet(
    conventionId: conventionId,
    fursuitId: fursuitId,
    cancellation: cancellation,
  );

  /// Revoke the owner's current opaque catch credential and create a replacement. The request accepts zero body bytes only and is not catch authorization.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i25.ConventionFursuitCatchCredentialRotateResponse,
      _i18.Response
    >
  >
  conventionFursuitCatchCredentialRotate({
    required _i15.int conventionId,
    required _i15.int fursuitId,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitCatchCredentialRotate(
    conventionId: conventionId,
    fursuitId: fursuitId,
    cancellation: cancellation,
  );

  /// Idempotently set the desired current catchability. A live session has a fixed 12-hour expiration; is_active is computed from unexpired session state and current operational participation. This endpoint is not catch authorization and catch creation must revalidate its own requirements.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i26.ConventionFursuitCatchSessionSetStateResponse,
      _i18.Response
    >
  >
  conventionFursuitCatchSessionSetState({
    required _i27.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel
    body,
    required _i15.int conventionId,
    required _i15.int fursuitId,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionFursuitCatchSessionSetState(
    body: body,
    conventionId: conventionId,
    fursuitId: fursuitId,
    cancellation: cancellation,
  );

  /// Retrieve convention
  /// Retrieve convention details by internal ID.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i28.ConventionsRetrieveResponse, _i18.Response>>
  conventionsRetrieve({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionsRetrieve(id: id, cancellation: cancellation);

  /// Get active convention
  /// Retrieve the authenticated player's currently selected active convention enrollment, if any.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i29.ConventionsActiveRetrieveResponse, _i18.Response>
  >
  conventionsActiveRetrieve({_i16.TonikCancellation? cancellation}) async =>
      _conventionsActiveRetrieve(cancellation: cancellation);

  /// Select active convention
  /// Explicitly select an enrolled active convention as the player's active gameplay context.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i30.ConventionsActiveUpdateResponse, _i18.Response>
  >
  conventionsActiveUpdate({
    required _i31.ApiConventionsActivePutBodyRequestBody body,
    _i16.TonikCancellation? cancellation,
  }) async => _conventionsActiveUpdate(body: body, cancellation: cancellation);

  /// Clear active convention
  /// Clear the authenticated player's active convention selection.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i32.ConventionsActiveDestroyResponse, _i18.Response>
  >
  conventionsActiveDestroy({_i16.TonikCancellation? cancellation}) async =>
      _conventionsActiveDestroy(cancellation: cancellation);

  /// List convention enrollments
  /// Retrieve a list of all convention enrollments for the authenticated player.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i33.ConventionsEnrollmentsListResponse, _i18.Response>
  >
  conventionsEnrollmentsList({_i16.TonikCancellation? cancellation}) async =>
      _conventionsEnrollmentsList(cancellation: cancellation);

  /// Enroll in convention
  /// Enroll the authenticated player into an active convention. Idempotent on retry.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i34.ConventionsEnrollmentsCreateResponse, _i18.Response>
  >
  conventionsEnrollmentsCreate({
    required _i35.ApiConventionsEnrollmentsPostBodyRequestBody body,
    _i16.TonikCancellation? cancellation,
  }) async =>
      _conventionsEnrollmentsCreate(body: body, cancellation: cancellation);
}
