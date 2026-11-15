import hashlib
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_tool", REPO / "tools/fetch_minecraft_server.py")
fetch_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_tool)

JAR = b"pretend server jar"
SHA1 = hashlib.sha1(JAR).hexdigest()


def fake_fetch(url):
    if url == fetch_tool.MANIFEST_URL:
        return json.dumps({"versions": [{"id": fetch_tool.VERSION, "url": "https://example.invalid/v.json"},
                                        {"id": "1.20", "url": "https://example.invalid/other.json"}]}).encode()
    if url == "https://example.invalid/v.json":
        return json.dumps({"downloads": {"server": {"url": "https://example.invalid/server.jar",
                                                    "sha1": SHA1}}}).encode()
    if url == "https://example.invalid/server.jar":
        return JAR
    raise AssertionError(url)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAFTPIPE_MINECRAFT_DIR", str(tmp_path / "mc"))
    return tmp_path / "mc"


def test_cache_dir_follows_env_and_has_a_default(cache, monkeypatch):
    assert fetch_tool.cache_dir() == cache
    monkeypatch.delenv("CRAFTPIPE_MINECRAFT_DIR")
    assert fetch_tool.cache_dir() == pathlib.Path.home() / ".cache/craftpipe/minecraft" / fetch_tool.VERSION


def test_status_reports_missing_jar(cache):
    ready, message = fetch_tool.status()
    assert ready is False and "tools/fetch_minecraft_server.py" in message


def test_download_without_flag_writes_jar_but_no_marker(cache):
    assert fetch_tool.main([], fetch=fake_fetch) == 0
    assert (cache / "server.jar").read_bytes() == JAR
    assert (cache / "server.jar.sha1").read_text().strip() == SHA1
    assert not (cache / "eula-accepted").exists()
    ready, message = fetch_tool.status()
    assert ready is False and "--accept-eula" in message


def test_accept_eula_writes_marker(cache):
    assert fetch_tool.main(["--accept-eula"], fetch=fake_fetch) == 0
    marker = (cache / "eula-accepted").read_text()
    assert "https://aka.ms/MinecraftEULA" in marker
    assert fetch_tool.status()[0] is True


def test_existing_good_jar_is_not_downloaded_again(cache):
    fetch_tool.main(["--accept-eula"], fetch=fake_fetch)

    def no_network(url):
        raise AssertionError("should not fetch " + url)
    assert fetch_tool.main([], fetch=no_network) == 0


def test_corrupt_jar_is_rejected(cache):
    fetch_tool.main(["--accept-eula"], fetch=fake_fetch)
    (cache / "server.jar").write_bytes(b"truncated")
    ready, message = fetch_tool.status()
    assert ready is False and "fetch_minecraft_server.py" in message and "corrupt" in message


def test_download_with_wrong_checksum_is_not_kept(cache):
    def bad(url):
        return b"evil" if url.endswith("server.jar") else fake_fetch(url)
    assert fetch_tool.main([], fetch=bad) != 0
    assert not (cache / "server.jar").exists()
