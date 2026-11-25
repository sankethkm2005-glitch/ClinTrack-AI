"""Phase 1 foundation tests for health check and static asset safety."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    """Verify /api/health returns 200 and reports SQLite connectivity."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["app"] == "ClinTrace AI"


def test_landing_page_serves_html():
    """Verify root URL serves the frontend landing page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ClinTrace AI" in response.text


def test_frontend_routes_served():
    """Verify all required frontend pages load with 200 OK and query params work."""
    routes = [
        "/",
        "/login.html?role=patient",
        "/login.html?role=doctor",
        "/signup.html",
        "/patient/dashboard.html",
        "/patient/documents.html",
        "/doctor/dashboard.html",
        "/doctor/workspace.html",
        "/css/styles.css",
        "/js/api.js",
    ]
    for r in routes:
        res = client.get(r)
        assert res.status_code == 200, f"Route '{r}' returned {res.status_code}"


def test_private_storage_is_not_publicly_mounted():
    """Ensure private upload storage is never accessible as a public URL."""
    response = client.get("/storage/uploads/.gitkeep")
    assert response.status_code == 404
