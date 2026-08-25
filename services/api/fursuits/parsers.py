"""Cardinality-aware multipart parsing for the fursuit HTTP surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from rest_framework.exceptions import ErrorDetail, ParseError
from rest_framework.parsers import DataAndFiles, MultiPartParser


@dataclass(frozen=True, slots=True)
class MultipartContract:
    """The exact value and file keys an endpoint accepts."""

    value_fields: frozenset[str]
    file_fields: frozenset[str]


class ClosedMultiPartParser(MultiPartParser):
    """Reject multipart keys and repeated parts before serializer collapsing."""

    def parse(
        self,
        stream: Any,
        media_type: str | None = None,
        parser_context: Mapping[str, Any] | None = None,
    ) -> DataAndFiles[Any, Any]:
        try:
            parsed: Any = super().parse(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                stream, media_type, parser_context
            )
        except ParseError:
            raise ParseError(
                {
                    "photo": [
                        ErrorDetail("Upload a valid image.", code="invalid")
                    ]
                }
            ) from None
        if parser_context is None:
            raise RuntimeError("multipart parser context is required")
        contract = cast(MultipartContract, parser_context["view"].multipart_contract)
        value_invalid = (
            frozenset(parsed.data.keys()) != contract.value_fields
            or any(len(parsed.data.getlist(field)) != 1 for field in parsed.data)
        )
        file_invalid = (
            frozenset(parsed.files.keys()) != contract.file_fields
            or any(len(parsed.files.getlist(field)) != 1 for field in parsed.files)
        )
        if value_invalid or file_invalid:
            errors: dict[str, list[ErrorDetail]] = {}
            if value_invalid:
                field = next(iter(contract.value_fields or contract.file_fields))
                errors[field] = [
                    ErrorDetail(
                        "Provide exactly the documented multipart fields.",
                        code="invalid",
                    )
                ]
            if file_invalid:
                field = next(iter(contract.file_fields or contract.value_fields))
                errors[field] = [
                    ErrorDetail(
                        "Provide exactly one valid uploaded photo.",
                        code="invalid",
                    )
                ]
            raise ParseError(errors)
        return parsed
