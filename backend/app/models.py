"""SQLAlchemy ORM models.

Attempts store a snapshot of every question they were taken with, so editing or
deleting a test later never changes historical results.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Test(TimestampMixin, Base):
    __tablename__ = "tests"
    __test__ = False  # stop pytest from trying to collect this class

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(String(100), default="", index=True)
    topic: Mapped[str] = mapped_column(String(150), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    marks_per_question: Mapped[float] = mapped_column(Float, default=1.0)
    negative_marks: Mapped[float] = mapped_column(Float, default=0.0)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    generation_notes: Mapped[str] = mapped_column(Text, default="")

    questions: Mapped[list["Question"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="Question.position",
    )
    attempts: Mapped[list["Attempt"]] = relationship(back_populates="test", passive_deletes=True)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_option: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(150), default="")
    # Where the question came from, e.g. "Biology Textbook, p. 42" (library generation).
    source_ref: Mapped[str] = mapped_column(String(300), default="")

    test: Mapped[Test] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        # At most one in-progress attempt per test, enforced by the database.
        Index(
            "uq_attempt_in_progress_per_test",
            "test_id",
            unique=True,
            sqlite_where=text("status = 'in_progress'"),
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    test_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot of test metadata at the time the attempt started.
    test_title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(100), default="")
    topic: Mapped[str] = mapped_column(String(150), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    duration_seconds: Mapped[int] = mapped_column(Integer)
    marks_per_question: Mapped[float] = mapped_column(Float)
    negative_marks: Mapped[float] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    submit_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0)
    unanswered_count: Mapped[int] = mapped_column(Integer, default=0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    test: Mapped[Test | None] = relationship(back_populates="attempts")
    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="AttemptAnswer.position",
    )


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "position", name="uq_attempt_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    # Question snapshot, with options stored in the order they were displayed.
    question_text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_option: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(150), default="")
    source_ref: Mapped[str] = mapped_column(String(300), default="")

    selected_option: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marked_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marks_awarded: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")


class Source(TimestampMixin, Base):
    """A document or web page in the library, split into searchable chunks (RAG)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    title_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # user-chosen title: keep on re-index
    kind: Mapped[str] = mapped_column(String(10))  # "file" | "url"
    file_type: Mapped[str] = mapped_column(String(10), default="")  # pdf, docx, txt, md, epub, html
    origin: Mapped[str] = mapped_column(String(2000), default="")  # file name or URL
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    chunks: Mapped[list["SourceChunk"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceChunk.position",
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (UniqueConstraint("source_id", "position", name="uq_chunk_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(300), default="")
    # L2-normalised float32 vector; NULL when indexed without embeddings (keyword search only).
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    source: Mapped[Source] = relationship(back_populates="chunks")
