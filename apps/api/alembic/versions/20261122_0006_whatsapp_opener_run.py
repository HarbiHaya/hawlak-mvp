"""Allow the WhatsApp opener run: an approved template that opens the 24-hour window.

Revision ID: 20261122_0006
Revises: 20261113_0005
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261122_0006"
down_revision: str | None = "20261113_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'discharge_voice_note', 'medication_reminder', 'follow_up_call', 'photo_request'"


def _kinds(extra: str = "") -> None:
    with op.batch_alter_table("delivery_runs") as batch:
        batch.drop_constraint("ck_delivery_runs_kind", type_="check")
        batch.create_check_constraint("ck_delivery_runs_kind", f"kind IN ({KINDS}{extra})")


def upgrade() -> None:
    _kinds(", 'whatsapp_opener'")


def downgrade() -> None:
    op.execute("DELETE FROM delivery_runs WHERE kind = 'whatsapp_opener'")
    _kinds()
