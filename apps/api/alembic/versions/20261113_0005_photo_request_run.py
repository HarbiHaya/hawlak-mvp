"""Allow the photo-request delivery run that asks the patient for each medicine box.

Revision ID: 20261113_0005
Revises: 20261113_0004
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261113_0005"
down_revision: str | None = "20261113_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'discharge_voice_note', 'medication_reminder', 'follow_up_call'"


def _kinds(extra: str = "") -> None:
    with op.batch_alter_table("delivery_runs") as batch:
        batch.drop_constraint("ck_delivery_runs_kind", type_="check")
        batch.create_check_constraint("ck_delivery_runs_kind", f"kind IN ({KINDS}{extra})")


def upgrade() -> None:
    _kinds(", 'photo_request'")


def downgrade() -> None:
    op.execute("DELETE FROM delivery_runs WHERE kind = 'photo_request'")
    _kinds()
