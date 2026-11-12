"""Add the insurer-reviewed care journey and delivery queue.

Revision ID: 20261112_0002
Revises: 20261104_0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261112_0002"
down_revision: str | None = "20261104_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "care_journeys",
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("preferred_form_of_address", sa.String(length=200), nullable=True),
        sa.Column("language_code", sa.String(length=20), nullable=False),
        sa.Column("source_document", JSON_VALUE, nullable=False),
        sa.Column("discharge_voice_note", JSON_VALUE, nullable=False),
        sa.Column("medications", JSON_VALUE, nullable=False),
        sa.Column("call_plan", JSON_VALUE, nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "review_status IN ('draft', 'approved')", name="ck_care_journeys_review_status"
        ),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("approval_idempotency_key"),
    )
    op.create_index(
        "ix_care_journeys_review_status", "care_journeys", ["review_status", "updated_at"]
    )

    op.create_table(
        "delivery_runs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("content_ref", sa.String(length=200), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "kind IN ('discharge_voice_note', 'medication_reminder', 'follow_up_call')",
            name="ck_delivery_runs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'sent', 'completed', 'failed', 'transferred')",
            name="ck_delivery_runs_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_delivery_runs_idempotency_key"),
    )
    op.create_index("ix_delivery_runs_case_status", "delivery_runs", ["case_id", "status"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_alerts_status"),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_alerts_idempotency_key"),
    )
    op.create_index("ix_alerts_case_status", "alerts", ["case_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_alerts_case_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_delivery_runs_case_status", table_name="delivery_runs")
    op.drop_table("delivery_runs")
    op.drop_index("ix_care_journeys_review_status", table_name="care_journeys")
    op.drop_table("care_journeys")
