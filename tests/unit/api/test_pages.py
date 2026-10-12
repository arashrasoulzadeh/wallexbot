"""The web pages: each renders its own content, works offline, and is translated."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from wallexbot.api.app import create_app
from wallexbot.config.defaults import default_config
from wallexbot.storage.repository import InMemoryRepository

UI = Path(__file__).resolve().parents[3] / "src" / "wallexbot" / "ui"
TEMPLATES = UI / "templates"
STATIC = UI / "static"
EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"

# page url -> text that only that page contains
PAGES = {
    "/dashboard": "dash.title",
    "/configure": "cfg.title",
    "/backtest": "bt.title",
    "/paper": "paper.title",
    "/runs": "runs.title",
    "/history": "hist.title",
    "/settings": "na.title",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(repo=InMemoryRepository())) as c:
        yield c


@pytest.fixture(scope="module")
def i18n():
    return json.loads((STATIC / "i18n.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path,key", PAGES.items())
def test_every_page_renders_its_own_content(client, path, key):
    """Regression: base.html had no content block, so all pages served the same empty shell."""
    html = client.get(path).text
    assert f'data-i18n="{key}"' in html
    assert 'data-i18n="banner.paper"' in html  # the paper-mode banner is on every page


def test_pages_are_different_from_each_other(client):
    bodies = {
        client.get(p).text for p in ("/dashboard", "/configure", "/backtest", "/paper", "/runs")
    }
    assert len(bodies) == 5


def test_the_root_is_the_dashboard(client):
    assert client.get("/").text == client.get("/dashboard").text


def test_navigation_marks_the_current_page(client):
    html = client.get("/paper").text
    assert re.search(r'class="active"[^>]*data-i18n="nav.paper"', html)
    assert 'href="/runs"' in html and 'href="/history"' in html
    assert 'href="/settings"' not in html  # unfinished pages are not linked


def test_static_assets_are_served(client):
    for name in ("app.js", "app.css", "i18n.json"):
        assert client.get(f"/static/{name}").status_code == 200


def test_nothing_is_loaded_from_the_internet():
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r'(src|href)="https?://', text), template.name
    assert "https://" not in (STATIC / "app.js").read_text(encoding="utf-8")


def test_api_data_is_never_inserted_as_html():
    sources = [STATIC / "app.js", *TEMPLATES.glob("*.html")]
    for source in sources:
        assert "innerHTML" not in source.read_text(encoding="utf-8"), source.name


def test_both_languages_have_the_same_keys(i18n):
    assert set(i18n["en"]) == set(i18n["fa"])
    assert all(v.strip() for lang in i18n.values() for v in lang.values())


def test_every_translation_key_used_by_the_pages_exists(i18n):
    used: set[str] = set()
    for source in [STATIC / "app.js", *TEMPLATES.glob("*.html")]:
        text = source.read_text(encoding="utf-8")
        used |= set(re.findall(r'data-i18n(?:-title)?="([a-zA-Z0-9_.]+)"', text))
        used |= set(re.findall(r"""wb\.t\('([a-zA-Z0-9_.]+)'""", text))
        used |= set(re.findall(r"""\['((?:m|cfg|paper|col|runs|bt)\.[a-zA-Z0-9_.]+)'""", text))
    used = {k for k in used if not k.endswith(".")}  # prefixes of keys built at run time
    # keys built from a value at run time
    used |= {
        f"state.{s}"
        for s in ("idle", "running", "paused", "stopped", "halted", "failed", "done", "unknown")
    }
    used |= {f"side.{s}" for s in ("BUY", "SELL")}
    used |= {f"nav.{p}" for p in ("dashboard", "configure", "backtest", "paper", "history", "runs")}
    missing = sorted(k for k in used if k not in i18n["en"])
    assert not missing, f"keys used but not translated: {missing}"


def test_inline_scripts_are_valid_javascript(tmp_path):
    node = shutil.which("node")
    command = ["bash", "-lc", "source ~/.nvm/nvm.sh >/dev/null 2>&1; node --version"]
    if node is None and subprocess.run(command, capture_output=True).returncode != 0:
        pytest.skip("node is not available")
    scripts = [("app.js", (STATIC / "app.js").read_text(encoding="utf-8"))]
    for template in TEMPLATES.glob("*.html"):
        for i, body in enumerate(
            re.findall(r"<script>(.*?)</script>", template.read_text(encoding="utf-8"), re.S)
        ):
            scripts.append((f"{template.name}#{i}", body))
    for name, body in scripts:
        path = tmp_path / (re.sub(r"\W", "_", name) + ".js")
        path.write_text(body, encoding="utf-8")
        result = subprocess.run(
            ["bash", "-lc", f"source ~/.nvm/nvm.sh >/dev/null 2>&1; node --check {path}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_the_default_config_matches_the_example_file():
    """The UI shows defaults from code; the CLI example is a file. They must not drift apart."""
    example = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    defaults = default_config()
    for section in ("market", "risk", "simulation"):
        for key, value in example[section].items():
            assert str(defaults[section].get(key)) == str(value), (section, key)
    assert defaults["strategy"]["grid"]["lower_price"] == example["strategy"]["grid"]["lower_price"]
    assert defaults["strategy"]["grid"]["grid_count"] == example["strategy"]["grid"]["grid_count"]
