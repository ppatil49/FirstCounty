"""Database tables. SQLite locally; any SQLAlchemy URL (Azure SQL, Postgres) in production."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20))
    product_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    versions: Mapped[list["Version"]] = relationship(back_populates="submission", order_by="Version.number")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="submission", order_by="Decision.id")


class Version(Base):
    __tablename__ = "versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"))
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Filled by the AI review
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission: Mapped[Submission] = relationship(back_populates="versions")
    findings: Mapped[list["Finding"]] = relationship(back_populates="version", order_by="Finding.id")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versions.id"))
    issue_code: Mapped[str] = mapped_column(String(50))
    regulation: Mapped[str] = mapped_column(String(200))
    offending_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[Version] = relationship(back_populates="findings")
    responses: Mapped[list["FindingResponse"]] = relationship(order_by="FindingResponse.id")
    feedback: Mapped[list["FindingFeedback"]] = relationship(order_by="FindingFeedback.id")

    @property
    def latest_response(self) -> "FindingResponse | None":
        return self.responses[-1] if self.responses else None

    @property
    def latest_feedback(self) -> "FindingFeedback | None":
        return self.feedback[-1] if self.feedback else None


class FindingResponse(Base):
    """Marketing's answer to a finding. Changing your mind adds a new row; the latest wins."""
    __tablename__ = "finding_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))
    action: Mapped[str] = mapped_column(String(10))  # accept | dispute
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FindingFeedback(Base):
    """Compliance's verdict on whether the AI finding was right; training signal for later."""
    __tablename__ = "finding_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))
    verdict: Mapped[str] = mapped_column(String(10))  # correct | incorrect
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))  # APPROVED | RETURNED | REJECTED
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submission: Mapped[Submission] = relationship(back_populates="decisions")


class AuditEvent(Base):
    """Append-only. Each row carries a hash of the previous row, so any edit breaks the chain."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(50))
    submission_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AuditImmutableError(RuntimeError):
    pass


@event.listens_for(AuditEvent, "before_update")
def _block_audit_update(mapper, connection, target):
    raise AuditImmutableError("Audit events are append-only and cannot be updated.")


@event.listens_for(AuditEvent, "before_delete")
def _block_audit_delete(mapper, connection, target):
    raise AuditImmutableError("Audit events are append-only and cannot be deleted.")


_SQLITE_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;""",
    """CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;""",
]


def make_session_factory(database_url: str) -> sessionmaker:
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        # Second line of defence at the database level, beyond the ORM guards above.
        with engine.begin() as conn:
            for ddl in _SQLITE_TRIGGERS:
                conn.execute(text(ddl))
    return sessionmaker(engine, expire_on_commit=False)
