import base64
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from devon_quote import server
from devon_quote.service import find_template

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "tests" / "fixtures" / "sample_ais_divi.sif"

pytestmark = pytest.mark.skipif(find_template() is None, reason="put the Devon calculator .xlsm at the top of the repo")


@pytest.fixture
def base_url(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "OUT", tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_page_and_status(base_url):
    with urllib.request.urlopen(base_url + "/") as r:
        assert b"Devon quote builder" in r.read()
    with urllib.request.urlopen(base_url + "/api/status") as r:
        assert json.loads(r.read())["items"] > 300


def test_build_and_download(base_url):
    b64 = base64.b64encode(SAMPLE.read_bytes()).decode()
    status, res = post(base_url + "/api/quote", {
        "bom": {"name": SAMPLE.name, "data": b64}, "project": "Web Test", "grade": "keystone",
        "stations": "30", "delivery": "4,500", "drawings": ["plan.pdf"], "notes": "all ends finished",
    })
    assert status == 200, res
    assert res["estimate"]["total"] == pytest.approx(22764.84, abs=0.01)
    assert not res["unmapped"] and res["review"]
    with urllib.request.urlopen(base_url + res["files"]["quote"]) as r:
        assert r.read()[:2] == b"PK"
    with urllib.request.urlopen(base_url + res["files"]["report"]) as r:
        text = r.read().decode()
        assert "all ends finished" in text and "plan.pdf" in text


def test_bad_inputs(base_url):
    status, res = post(base_url + "/api/quote", {})
    assert status == 400 and "Missing" in res["error"]
    status, res = post(base_url + "/api/template", {"file": {"name": "x.xlsm", "data": base64.b64encode(b"nope").decode()}})
    assert status == 400
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base_url + "/download/../../etc/passwd")
