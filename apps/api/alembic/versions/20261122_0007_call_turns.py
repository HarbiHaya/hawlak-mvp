"""Store each spoken turn of a follow-up call for the care team.

Revision ID: 20261122_0007
Revises: 20261122_0006
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261122_0007"
down_revision: str | None = "20261122_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_turns",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("delivery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer_kind", sa.String(32), nullable=True),
        sa.Column("guard", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "seq", name="uq_call_turns_run_seq"),
        sa.CheckConstraint("speaker IN ('agent', 'patient')", name="ck_call_turns_speaker"),
    )
    op.create_index("ix_call_turns_run_id", "call_turns", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_call_turns_run_id", table_name="call_turns")
    op.drop_table("call_turns")
