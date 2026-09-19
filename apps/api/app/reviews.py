"""Evidence-linked manuscript review findings."""

from contextlib import nullcontext
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import ReviewFinding


def record_finding(
    session: Session,
    *,
    revision_id: UUID | None,
    artifact_id: UUID | None,
    severity: str,
    criterion: str,
    evidence: str,
    manage_transaction: bool = True,
) -> UUID:
    """Persist a review finding without changing the reviewed content."""

    if revision_id is None and artifact_id is None:
        raise ValueError("finding must reference a revision or artifact")
    with (session.begin() if manage_transaction else nullcontext()):
        finding = ReviewFinding(
            revision_id=revision_id,
            artifact_id=artifact_id,
            severity=severity,
            criterion=criterion,
            evidence=evidence,
        )
        session.add(finding)
        session.flush()
        return finding.id
