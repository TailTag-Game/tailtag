// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i3;
import 'dart:core' as _i2;

import 'package:tonik_util/tonik_util.dart' as _i1;

enum ApiSchemaParametersModel
    implements
        _i1.MatrixEncodable,
        _i1.LabelEncodable,
        _i1.SimpleEncodable,
        _i1.FormEncodable,
        _i1.JsonEncodable,
        _i1.UriEncodable {
  af(r'af'),
  ar(r'ar'),
  arDz(r'ar-dz'),
  ast(r'ast'),
  az(r'az'),
  be(r'be'),
  bg(r'bg'),
  bn(r'bn'),
  br(r'br'),
  bs(r'bs'),
  ca(r'ca'),
  ckb(r'ckb'),
  cs(r'cs'),
  cy(r'cy'),
  da(r'da'),
  de(r'de'),
  dsb(r'dsb'),
  el(r'el'),
  en(r'en'),
  enAu(r'en-au'),
  enGb(r'en-gb'),
  eo(r'eo'),
  es(r'es'),
  esAr(r'es-ar'),
  esCo(r'es-co'),
  esMx(r'es-mx'),
  esNi(r'es-ni'),
  esVe(r'es-ve'),
  et(r'et'),
  eu(r'eu'),
  fa(r'fa'),
  fi(r'fi'),
  fr(r'fr'),
  fy(r'fy'),
  ga(r'ga'),
  gd(r'gd'),
  gl(r'gl'),
  he(r'he'),
  hi(r'hi'),
  hr(r'hr'),
  hsb(r'hsb'),
  ht(r'ht'),
  hu(r'hu'),
  hy(r'hy'),
  ia(r'ia'),
  id(r'id'),
  ig(r'ig'),
  io(r'io'),
  $is(r'is'),
  it(r'it'),
  ja(r'ja'),
  ka(r'ka'),
  kab(r'kab'),
  kk(r'kk'),
  km(r'km'),
  kn(r'kn'),
  ko(r'ko'),
  ky(r'ky'),
  lb(r'lb'),
  lt(r'lt'),
  lv(r'lv'),
  mk(r'mk'),
  ml(r'ml'),
  mn(r'mn'),
  mr(r'mr'),
  ms(r'ms'),
  my(r'my'),
  nb(r'nb'),
  ne(r'ne'),
  nl(r'nl'),
  nn(r'nn'),
  os(r'os'),
  pa(r'pa'),
  pl(r'pl'),
  pt(r'pt'),
  ptBr(r'pt-br'),
  ro(r'ro'),
  ru(r'ru'),
  sk(r'sk'),
  sl(r'sl'),
  sq(r'sq'),
  sr(r'sr'),
  srLatn(r'sr-latn'),
  sv(r'sv'),
  sw(r'sw'),
  ta(r'ta'),
  te(r'te'),
  tg(r'tg'),
  th(r'th'),
  tk(r'tk'),
  tr(r'tr'),
  tt(r'tt'),
  udm(r'udm'),
  ug(r'ug'),
  uk(r'uk'),
  ur(r'ur'),
  uz(r'uz'),
  vi(r'vi'),
  zhHans(r'zh-hans'),
  zhHant(r'zh-hant');

  const ApiSchemaParametersModel(this._$rawValue);

  factory ApiSchemaParametersModel.fromJson(_i2.dynamic value) {
    if (value is! _i2.String) {
      throw _i1.JsonDecodingException(
        r'Expected String for ApiSchemaParametersModel, got ${value.runtimeType}',
      );
    }
    return values.firstWhere(
      (e) => e._$rawValue == value,
      orElse: () => throw _i1.JsonDecodingException(
        r'No matching ApiSchemaParametersModel for value: $value',
      ),
    );
  }

  factory ApiSchemaParametersModel.fromSimple(
    _i2.String? value, {
    required _i2.bool explode,
    _i2.String? context,
  }) {
    return ApiSchemaParametersModel.fromJson(
      value.decodeSimpleString(context: context),
    );
  }

  factory ApiSchemaParametersModel.fromForm(
    _i2.String? value, {
    required _i2.bool explode,
    _i2.String? context,
  }) {
    return ApiSchemaParametersModel.fromJson(
      value.decodeFormString(context: context),
    );
  }

  final _i2.String _$rawValue;

  @_i2.override
  _i2.String toJson() => _$rawValue;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.simple;

  @_i2.override
  _i2.String toSimple({
    required _i2.bool explode,
    required _i2.bool allowEmpty,
    _i2.bool literal = false,
  }) => _$rawValue.toSimple(
    explode: explode,
    allowEmpty: allowEmpty,
    literal: literal,
  );

  @_i2.override
  _i2.List<_i1.ParameterEntry> toForm(
    _i2.String paramName, {
    required _i2.bool explode,
    required _i2.bool allowEmpty,
    required _i3.Encoding textEncoding,
    _i2.bool useQueryComponent = false,
    _i2.bool allowReserved = false,
    _i2.Map<_i2.String, _i1.FormFieldEncoding> fieldEncodings = const {},
  }) => _$rawValue.toForm(
    paramName,
    explode: explode,
    allowEmpty: allowEmpty,
    useQueryComponent: useQueryComponent,
    allowReserved: allowReserved,
    textEncoding: textEncoding,
  );

  @_i2.override
  _i2.String toLabel({
    required _i2.bool explode,
    required _i2.bool allowEmpty,
  }) => _$rawValue.toLabel(explode: explode, allowEmpty: allowEmpty);

  @_i2.override
  _i2.String uriEncode({
    required _i2.bool allowEmpty,
    required _i3.Encoding textEncoding,
    _i2.bool useQueryComponent = false,
    _i2.bool allowReserved = false,
  }) => _$rawValue.uriEncode(
    allowEmpty: allowEmpty,
    textEncoding: textEncoding,
    useQueryComponent: useQueryComponent,
    allowReserved: allowReserved,
  );

  @_i2.override
  _i2.String toMatrix(
    _i2.String paramName, {
    required _i2.bool explode,
    required _i2.bool allowEmpty,
  }) =>
      _$rawValue.toMatrix(paramName, explode: explode, allowEmpty: allowEmpty);
}
