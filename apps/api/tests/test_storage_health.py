from app.main import app
from app.services.object_storage import get_object_storage


class HealthyStorage:
    bucket = "hawlak-mvp"

    def ensure_bucket(self):
        return None


def test_storage_health_checks_the_bucket(client):
    app.dependency_overrides[get_object_storage] = lambda: HealthyStorage()

    response = client.get("/health/storage")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "bucket": "hawlak-mvp"}
