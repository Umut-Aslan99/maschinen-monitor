from pathlib import Path

from fastapi.testclient import TestClient

from monitor.app import create_app
from monitor.settings import Settings


def client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    (tmp_path / "assets" / "main-abc123.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    # Without the context manager the lifespan (database, MQTT) does not start – static serving needs neither.
    return TestClient(create_app(Settings(static_dir=str(tmp_path))))


def test_client_routes_get_the_app_shell_also_for_head(tmp_path: Path) -> None:
    c = client(tmp_path)
    for method in ("GET", "HEAD"):
        r = c.request(method, "/maschine/SGM-01")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
    assert "<title>app</title>" in c.get("/").text


def test_hashed_assets_are_cached_and_nothing_outside_the_build_is_served(tmp_path: Path) -> None:
    c = client(tmp_path)
    r = c.get("/assets/main-abc123.js")
    assert r.text == "console.log(1)"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "nope" not in c.get("/../secret.txt").text
    assert "nope" not in c.get("/%2e%2e/secret.txt").text
    assert c.get("/api/unknown").status_code == 404
