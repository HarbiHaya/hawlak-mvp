"""Create the synthetic Hawlak demo schema.

Revision ID: 20261104_0001
Revises: None
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "patient_cases",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("patient_alias", sa.String(length=200), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("dialect_code", sa.String(length=50), nullable=False),
        sa.Column("expected_box_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("expected_box_count > 0", name="ck_patient_cases_expected_box_count"),
        sa.CheckConstraint(
            "status IN ('active', 'photo_collection', 'review_requested', 'completed')",
            name="ck_patient_cases_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_cases_phone_status", "patient_cases", ["phone_e164", "status"])

    op.create_table(
        "approved_plans",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinical_facts", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("version > 0", name="ck_approved_plans_version"),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "version", name="uq_approved_plans_case_version"),
    )
    op.create_index("ix_approved_plans_case_id", "approved_plans", ["case_id"])

    op.create_table(
        "voice_artifacts",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("voice", sa.String(length=200), nullable=True),
        sa.Column("generated_script_ar", sa.Text(), nullable=True),
        sa.Column("generated_script_sha256", sa.String(length=128), nullable=True),
        sa.Column("approval_status", sa.String(length=20), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_script_sha256", sa.String(length=128), nullable=True),
        sa.Column("audio_object_key", sa.String(length=1024), nullable=True),
        sa.Column("audio_checksum", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "approval_status IN ('draft', 'approved', 'rejected')",
            name="ck_voice_artifacts_approval_status",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["approved_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "prompt_version", name="uq_voice_artifacts_plan_prompt_version"
        ),
    )
    op.create_index("ix_voice_artifacts_plan_id", "voice_artifacts", ["plan_id"])

    op.create_table(
        "message_logs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=True),
        sa.Column("wa_message_id", sa.String(length=256), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("normalized_payload", JSON_VALUE, nullable=False),
        sa.Column("outbound_step", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("delivery_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')", name="ck_message_logs_direction"
        ),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "outbound_step", name="uq_message_logs_case_outbound_step"),
        sa.UniqueConstraint("idempotency_key", name="uq_message_logs_idempotency_key"),
        sa.UniqueConstraint("wa_message_id", name="uq_message_logs_wa_message_id"),
    )
    op.create_index("ix_message_logs_case_created", "message_logs", ["case_id", "created_at"])

    op.create_table(
        "inbound_media",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("message_log_id", sa.String(length=128), nullable=False),
        sa.Column("meta_media_id", sa.String(length=256), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("object_sha256", sa.String(length=128), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("processing_error", sa.String(length=200), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_log_id"], ["message_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_log_id", name="uq_inbound_media_message_log_id"),
    )
    op.create_index("ix_inbound_media_case_received", "inbound_media", ["case_id", "received_at"])

    op.create_table(
        "workflow_events",
        sa.Column("sequence", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("payload", JSON_VALUE, nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("event_version > 0", name="ck_workflow_events_version"),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sequence"),
        sa.UniqueConstraint("event_id", name="uq_workflow_events_event_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_events_idempotency_key"),
    )
    op.create_index("ix_workflow_events_case_sequence", "workflow_events", ["case_id", "sequence"])

    op.create_table(
        "review_outcomes",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("workflow_event_sequence", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "outcome IN ('matched', 'mismatch_found', 'unclear_photo', 'contact_patient')",
            name="ck_review_outcomes_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_event_sequence"], ["workflow_events.sequence"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_review_outcomes_idempotency_key"),
    )
    op.create_index("ix_review_outcomes_event", "review_outcomes", ["workflow_event_sequence"])


def downgrade() -> None:
    op.drop_index("ix_review_outcomes_event", table_name="review_outcomes")
    op.drop_table("review_outcomes")
    op.drop_index("ix_workflow_events_case_sequence", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_index("ix_inbound_media_case_received", table_name="inbound_media")
    op.drop_table("inbound_media")
    op.drop_index("ix_message_logs_case_created", table_name="message_logs")
    op.drop_table("message_logs")
    op.drop_index("ix_voice_artifacts_plan_id", table_name="voice_artifacts")
    op.drop_table("voice_artifacts")
    op.drop_index("ix_approved_plans_case_id", table_name="approved_plans")
    op.drop_table("approved_plans")
    op.drop_index("ix_patient_cases_phone_status", table_name="patient_cases")
    op.drop_table("patient_cases")
