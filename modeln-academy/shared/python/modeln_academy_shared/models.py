"""Validated data contracts shared by independently deployed services."""

from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, StringConstraints


class EvidenceClass(StrEnum):
    """Evidence classifications preserved from the canonical guide."""

    VERIFIED_IN_CODE = "verified_in_code"
    CONFIGURED = "configured"
    DOCUMENTED = "documented"
    ENVIRONMENT_SPECIFIC = "environment_specific"
    LEGACY_TEST_TEMPLATE = "legacy_test_template"
    UNCONFIRMED_GAP = "unconfirmed_gap"
    HYPOTHESIS = "hypothesis"


StableIdValue = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z0-9][a-z0-9_.:-]*$",
        strip_whitespace=True,
    ),
]


class StableId(BaseModel):
    """A URL-safe identifier that cannot expose a local filesystem path."""

    value: StableIdValue


class Citation(BaseModel):
    """A stable link from learning content to an evidenced guide section."""

    section_id: StableIdValue
    title: str = Field(min_length=1, max_length=240)
    evidence_class: EvidenceClass


class ApiError(BaseModel):
    """A safe error response with a traceable correlation identifier."""

    code: StableIdValue
    message: str = Field(min_length=1, max_length=240)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))


class ServiceHealth(BaseModel):
    """Uniform service health response."""

    service: StableIdValue
    status: str = Field(pattern=r"^(ok|degraded|unavailable)$")
    version: str = Field(min_length=1, max_length=64)

