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
        "call_turns",
    }

    with engine.begin() as connection:
        columns = "id, case_id, kind, status, idempotency_key, content_ref, scheduled_at"
        connection.exec_driver_sql(
            "INSERT INTO patient_cases (id, patient_alias, phone_e164, dialect_code, "
            "expected_box_count, status, created_at, updated_at) VALUES "
            "('c1', 'a', '+966500000000', 'ar-SA', 1, 'active', '2026-11-22', '2026-11-22')"
        )
        connection.exec_driver_sql(
            f"INSERT INTO delivery_runs ({columns}, created_at, updated_at) VALUES "
            "('r1', 'c1', 'whatsapp_opener', 'pending', 'k1', 'opener', '2026-11-22', "
            "'2026-11-22', '2026-11-22')"
        )

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    assert "patient_cases" in inspect(engine).get_table_names()
    engine.dispose()
