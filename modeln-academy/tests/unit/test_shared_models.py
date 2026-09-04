from uuid import UUID

import pytest
from modeln_academy_shared.models import ApiError, Citation, EvidenceClass, StableId
from pydantic import ValidationError


def test_evidence_class_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        EvidenceClass("probably_true")


@pytest.mark.parametrize("value", ["bad id", "/Users/person/source.py", "", "a/b"])
def test_stable_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError):
        StableId(value=value)


def test_api_error_requires_safe_message_and_correlation_id() -> None:
    error = ApiError(code="content_unavailable", message="Course content is unavailable.")

    assert UUID(error.correlation_id)
    assert error.message == "Course content is unavailable."


def test_citation_keeps_evidence_class_explicit() -> None:
    citation = Citation(
        section_id="chapter-5-a-reusable-beginner-trace",
        title="Chapter 5 — A Reusable Beginner Trace",
        evidence_class=EvidenceClass.VERIFIED_IN_CODE,
    )

    assert citation.evidence_class is EvidenceClass.VERIFIED_IN_CODE

