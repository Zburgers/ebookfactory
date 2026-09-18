from uuid import uuid4

import pytest

from app.tools import InvalidCapability, issue_capability, verify_capability
from app.providers import save_provider_setting


def test_capability_binds_scope_and_generation() -> None:
    project_id = uuid4()
    job_id = uuid4()
    token = issue_capability(
        "local-secret",
        project_id=project_id,
        job_id=job_id,
        generation=3,
        tool="read_sections",
    )

    capability = verify_capability(
        token,
        "local-secret",
        project_id=project_id,
        job_id=job_id,
        generation=3,
        tool="read_sections",
    )

    assert capability.project_id == project_id
    with pytest.raises(InvalidCapability):
        verify_capability(
            token,
            "local-secret",
            project_id=uuid4(),
            job_id=job_id,
            generation=3,
            tool="read_sections",
        )


def test_provider_endpoint_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError):
        save_provider_setting(
            None,  # validation runs before the transaction boundary
            provider="custom",
            scope="app",
            endpoint="https://user:bad-creds@example.test/v1",
            protocol="openai-compatible",
            credential_ref="local-key-ref",
            orchestration_model=None,
            drafting_model=None,
            review_model=None,
        )
