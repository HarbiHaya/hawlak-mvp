"""Let a registered caregiver send medicine photos, and keep each photo's label check.

Revision ID: 20261113_0004
Revises: 20261113_0003
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261113_0004"
down_revision: str | None = "20261113_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MEDIA_COLUMNS = (
    sa.Column("sender_role", sa.String(16), nullable=False, server_default="patient"),
    sa.Column("label_reading", JSON_VALUE, nullable=True),
    sa.Column("check_status", sa.String(32), nullable=True),
    sa.Column("medication_id", sa.String(128), nullable=True),
    sa.Column("review_status", sa.String(20), nullable=True),
    sa.Column("reviewed_by", sa.String(200), nullable=True),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    op.add_column("patient_cases", sa.Column("caregiver_phone_e164", sa.String(16), nullable=True))
    for column in MEDIA_COLUMNS:
        op.add_column("inbound_media", column)


def downgrade() -> None:
    with op.batch_alter_table("inbound_media") as batch:
        for column in reversed(MEDIA_COLUMNS):
            batch.drop_column(column.name)
    op.drop_column("patient_cases", "caregiver_phone_e164")
