from __future__ import annotations

from deli_rag.agent.validate import redact_pii, validate, verify_citations_exist
from deli_rag.schemas.answer import Answer


def test_pii_redaction_ssn():
    redacted, changed = redact_pii("SSN 123-45-6789 is on file")
    assert "[SSN-REDACTED]" in redacted
    assert changed is True


def test_pii_redaction_email_and_phone():
    redacted, changed = redact_pii("call 555-123-4567 or email a@b.com")
    assert "[EMAIL-REDACTED]" in redacted
    assert "[PHONE-REDACTED]" in redacted
    assert changed is True


def test_pii_no_change_on_clean_text():
    redacted, changed = redact_pii("The commission was 216.56")
    assert redacted == "The commission was 216.56"
    assert changed is False


def test_validate_ok():
    a = Answer(answer="216.56", citations=[1, 2], confidence=0.9, abstained=False)
    idx = [{"id": 1}, {"id": 2}]
    report = validate(a, evidence_index=idx)
    assert report.ok


def test_validate_bad_citation():
    a = Answer(answer="x", citations=[99], confidence=0.9, abstained=False)
    idx = [{"id": 1}]
    report = validate(a, evidence_index=idx)
    assert not report.ok
    assert any("citation ids" in i for i in report.issues)


def test_validate_empty_answer_not_abstained():
    a = Answer(answer="", citations=[1], confidence=0.9, abstained=False)
    idx = [{"id": 1}]
    report = validate(a, evidence_index=idx)
    assert not report.ok


def test_validate_abstained_ok_no_citations():
    a = Answer(answer="", citations=[], confidence=0.0, abstained=True, reason="insufficient")
    report = validate(a, evidence_index=[])
    assert report.ok


def test_verify_citations_exist():
    ok, bad = verify_citations_exist([1, 2, 3], [{"id": 1}, {"id": 3}])
    assert ok is False
    assert bad == [2]