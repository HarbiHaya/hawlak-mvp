from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

API_ROOT = Path(__file__).resolve().parents[1]


def test_initial_migration_upgrades_and_downgrades_sqlite(tmp_path):
    database = tmp_path / "migration.db"
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database}")
    assert set(inspect(engine).get_table_names()) >= {
        "patient_cases",
        "approved_plans",
        "voice_artifacts",
        "message_logs",
        "inbound_media",
        "workflow_events",
        "review_outcomes",
    }

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    assert "patient_cases" in inspect(engine).get_table_names()
    engine.dispose()
