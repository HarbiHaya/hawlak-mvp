"""Store the insurer coverage check and the generated draft on each journey.

Revision ID: 20261113_0003
Revises: 20261112_0002
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261113_0003"
down_revision: str | None = "20261112_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("care_journeys", sa.Column("insurance", JSON_VALUE, nullable=True))
    op.add_column("care_journeys", sa.Column("generated_draft", JSON_VALUE, nullable=True))


def downgrade() -> None:
    op.drop_column("care_journeys", "generated_draft")
    op.drop_column("care_journeys", "insurance")
