from sqlalchemy.exc import SQLAlchemyError

from app.db import get_db_session
from app.main import app


class FailingSession:
    def execute(self, _statement):
        raise SQLAlchemyError("driver detail with a pretend password")


def test_health_reports_database_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_health_reports_database_unavailable_without_driver_details(client):
    app.dependency_overrides[get_db_session] = lambda: FailingSession()

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert response.json()["status"] == "degraded"
    assert "password" not in response.text
    assert "driver" not in response.text
