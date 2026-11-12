def login(client, username: str, password: str = "synthetic-demo-password"):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def session_headers(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def test_demo_login_issues_a_role_scoped_session(client):
    response = login(client, "hospital")

    assert response.status_code == 200
    assert response.json()["role"] == "hospital"
    assert response.json()["username"] == "hospital"
    assert response.json()["displayName"] == "فريق المستشفى"
    assert response.json()["expiresAt"].endswith("Z")
    assert response.json()["accessToken"]


def test_demo_login_rejects_unknown_or_invalid_credentials(client):
    unknown = login(client, "unknown")
    invalid = login(client, "hospital", "wrong-password-long-enough")

    assert unknown.status_code == 401
    assert invalid.status_code == 401
    assert unknown.json() == {"error": "invalid_credentials"}
    assert invalid.json() == {"error": "invalid_credentials"}


def test_hospital_session_cannot_read_other_role_workspaces(client):
    hospital = login(client, "hospital")
    headers = session_headers(hospital)

    queue = client.get("/internal/workspace/cases", headers=headers)
    caregiver = client.get("/internal/caregiver/cases/case-demo", headers=headers)

    assert queue.status_code == 403
    assert caregiver.status_code == 403


def test_insurer_and_caregiver_sessions_are_separated(client):
    insurer = session_headers(login(client, "insurer"))
    caregiver = session_headers(login(client, "caregiver"))

    assert client.get("/internal/workspace/cases", headers=insurer).status_code == 200
    assert client.get("/internal/workspace/alerts", headers=insurer).status_code == 200
    assert client.get("/internal/caregiver/cases/missing", headers=insurer).status_code == 403

    assert client.get("/internal/workspace/cases", headers=caregiver).status_code == 403
    assert client.get("/internal/caregiver/cases/missing", headers=caregiver).status_code == 404


def test_admin_session_can_access_every_workspace(client):
    admin = session_headers(login(client, "admin"))

    assert client.get("/internal/workspace/cases", headers=admin).status_code == 200
    assert client.get("/internal/workspace/alerts", headers=admin).status_code == 200
    assert client.get("/internal/caregiver/cases/missing", headers=admin).status_code == 404


def test_session_cannot_access_service_only_routes(client):
    admin = session_headers(login(client, "admin"))

    response = client.get("/internal/review-events", headers=admin)

    assert response.status_code == 403
