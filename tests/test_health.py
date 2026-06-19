from fastapi.testclient import TestClient

from modules.app.main import app


def test_health():
    client = TestClient(app)
    res = client.get('/health')
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["preferred_model"] == "claude"


def test_home_page_renders_guided_form():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    # Guided, plain-language intake (no jargon labels).
    assert "¿Qué quieres lograr con esta app?" in res.text
    assert "Crear mi app" in res.text
