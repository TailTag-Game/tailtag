// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiProfilePatch200BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiProfilePatch200BodyModel({
    this.handle,
    this.displayName,
    this.avatarUrl,
    this.onboardingComplete,
    this.isEnabled,
  });

  factory ApiProfilePatch200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {
        r'handle',
        r'display_name',
        r'avatar_url',
        r'onboarding_complete',
        r'is_enabled',
      },
      listKeys: {},
      context: r'ApiProfilePatch200BodyModel',
    );
    return ApiProfilePatch200BodyModel(
      handle: _$values[r'handle'].decodeSimpleNullableString(
        context: r'ApiProfilePatch200BodyModel.handle',
      ),
      displayName: _$values[r'display_name'].decodeSimpleNullableString(
        context: r'ApiProfilePatch200BodyModel.display_name',
      ),
      avatarUrl: _$values[r'avatar_url'].decodeSimpleNullableUri(
        context: r'ApiProfilePatch200BodyModel.avatar_url',
      ),
      onboardingComplete: _$values[r'onboarding_complete'].decodeSimpleBool(
        context: r'ApiProfilePatch200BodyModel.onboarding_complete',
      ),
      isEnabled: _$values[r'is_enabled'].decodeSimpleBool(
        context: r'ApiProfilePatch200BodyModel.is_enabled',
      ),
    );
  }

  factory ApiProfilePatch200BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiProfilePatch200BodyModel');
    return ApiProfilePatch200BodyModel(
      handle: _$map[r'handle'].decodeJsonNullableString(
        context: r'ApiProfilePatch200BodyModel.handle',
      ),
      displayName: _$map[r'display_name'].decodeJsonNullableString(
        context: r'ApiProfilePatch200BodyModel.display_name',
      ),
      avatarUrl: _$map[r'avatar_url'].decodeJsonNullableUri(
        context: r'ApiProfilePatch200BodyModel.avatar_url',
      ),
      onboardingComplete: _$map[r'onboarding_complete'].decodeJsonBool(
        context: r'ApiProfilePatch200BodyModel.onboarding_complete',
      ),
      isEnabled: _$map[r'is_enabled'].decodeJsonBool(
        context: r'ApiProfilePatch200BodyModel.is_enabled',
      ),
    );
  }

  factory ApiProfilePatch200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {
        r'handle',
        r'display_name',
        r'avatar_url',
        r'onboarding_complete',
        r'is_enabled',
      },
      listKeys: {},
      context: r'ApiProfilePatch200BodyModel',
    );
    return ApiProfilePatch200BodyModel(
      handle: _$values[r'handle'].decodeFormNullableString(
        context: r'ApiProfilePatch200BodyModel.handle',
      ),
      displayName: _$values[r'display_name'].decodeFormNullableString(
        context: r'ApiProfilePatch200BodyModel.display_name',
      ),
      avatarUrl: _$values[r'avatar_url'].decodeFormNullableUri(
        context: r'ApiProfilePatch200BodyModel.avatar_url',
      ),
      onboardingComplete: _$values[r'onboarding_complete'].decodeFormBool(
        context: r'ApiProfilePatch200BodyModel.onboarding_complete',
      ),
      isEnabled: _$values[r'is_enabled'].decodeFormBool(
        context: r'ApiProfilePatch200BodyModel.is_enabled',
      ),
    );
  }

  final _i3.String? handle;

  final _i3.String? displayName;

  final _i3.Uri? avatarUrl;

  final _i3.bool? onboardingComplete;

  final _i3.bool? isEnabled;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ApiProfilePatch200BodyModelCopyWith<ApiProfilePatch200BodyModel>
  get copyWith => _ApiProfilePatch200BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePatch200BodyModel &&
        other.handle == this.handle &&
        other.displayName == this.displayName &&
        other.avatarUrl == this.avatarUrl &&
        other.onboardingComplete == this.onboardingComplete &&
        other.isEnabled == this.isEnabled;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      handle,
      displayName,
      avatarUrl,
      onboardingComplete,
      isEnabled,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    return <_i3.String, _i1.PropertyValue>{};
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiProfilePatch200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiProfilePatch200BodyModelCopyWith<$Res> {
  factory $$ApiProfilePatch200BodyModelCopyWith(
    ApiProfilePatch200BodyModel value,
  ) = _ApiProfilePatch200BodyModelCopyWith<$Res>;

  $Res call({
    _i3.String? handle,
    _i3.String? displayName,
    _i3.Uri? avatarUrl,
    _i3.bool? onboardingComplete,
    _i3.bool? isEnabled,
  });
  _i3.String? get handle;
  _i3.String? get displayName;
  _i3.Uri? get avatarUrl;
  _i3.bool? get onboardingComplete;
  _i3.bool? get isEnabled;
}

class _ApiProfilePatch200BodyModelCopyWith<$Res>
    implements $$ApiProfilePatch200BodyModelCopyWith<$Res> {
  _ApiProfilePatch200BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiProfilePatch200BodyModel _value;

  @_i3.override
  _i3.String? get handle => _value.handle;

  @_i3.override
  _i3.String? get displayName => _value.displayName;

  @_i3.override
  _i3.Uri? get avatarUrl => _value.avatarUrl;

  @_i3.override
  _i3.bool? get onboardingComplete => _value.onboardingComplete;

  @_i3.override
  _i3.bool? get isEnabled => _value.isEnabled;

  @_i3.override
  $Res call({
    _i3.Object? handle = _sentinel,
    _i3.Object? displayName = _sentinel,
    _i3.Object? avatarUrl = _sentinel,
    _i3.Object? onboardingComplete = _sentinel,
    _i3.Object? isEnabled = _sentinel,
  }) {
    return (ApiProfilePatch200BodyModel(
      handle: _i3.identical(handle, _sentinel)
          ? this.handle
          : (handle as _i3.String?),
      displayName: _i3.identical(displayName, _sentinel)
          ? this.displayName
          : (displayName as _i3.String?),
      avatarUrl: _i3.identical(avatarUrl, _sentinel)
          ? this.avatarUrl
          : (avatarUrl as _i3.Uri?),
      onboardingComplete: _i3.identical(onboardingComplete, _sentinel)
          ? this.onboardingComplete
          : (onboardingComplete as _i3.bool?),
      isEnabled: _i3.identical(isEnabled, _sentinel)
          ? this.isEnabled
          : (isEnabled as _i3.bool?),
    ) as $Res);
  }
}
