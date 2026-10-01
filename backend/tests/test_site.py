import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main  # noqa: E402
from app.site import create_site  # noqa: E402


def test_site_serves_frontend_and_api_under_prefix(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    monkeypatch.setitem(main.state, "retriever", SimpleNamespace(ready=True))
    client = TestClient(create_site(tmp_path))  # no `with`: the lifespan (index + model load) is not run
    assert 'id="root"' in client.get("/").text
    assert client.get("/api/health").json() == {"status": "ok", "search_model_ready": True}
    assert client.get("/health").status_code == 404  # the API lives only under /api
