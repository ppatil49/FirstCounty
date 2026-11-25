from __future__ import annotations

import pytest

from engine.reviewer import Reviewer
from tests.fakes.fake_llm import FakeLLM
from tests.helpers import BAD_AD, MARIA, default_responder
from workflow.models import make_session_factory
from workflow.service import WorkflowService


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM(default_responder)


@pytest.fixture
def session_factory(tmp_path):
    return make_session_factory(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


@pytest.fixture
def service(session_factory, fake_llm) -> WorkflowService:
    return WorkflowService(session_factory, lambda: Reviewer(fake_llm, 0.6))


@pytest.fixture
def reviewed(service) -> str:
    """A submission sitting in AI_REVIEWED with one high and one low finding."""
    return service.submit(MARIA, "CD postcard", "mailer", "deposit", BAD_AD)
