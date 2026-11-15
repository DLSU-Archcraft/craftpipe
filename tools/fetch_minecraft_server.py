#!/usr/bin/env python3
"""Download the official Minecraft server used by the parity tests.

    python tools/fetch_minecraft_server.py [--accept-eula]

The jar comes straight from Mojang, is checked against the SHA-1 Mojang
publishes, and is kept in a per-user cache (never in this repository; it
may not be redistributed). Running the server requires accepting the
Minecraft EULA (https://aka.ms/MinecraftEULA). Pass --accept-eula to
record that *you* accept it; the tests only write eula=true when that
record exists.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

VERSION = "1.21.1"
MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
EULA_URL = "https://aka.ms/MinecraftEULA"
COMMAND = "python tools/fetch_minecraft_server.py"


def cache_dir() -> pathlib.Path:
    override = os.environ.get("CRAFTPIPE_MINECRAFT_DIR")
    if override:
        return pathlib.Path(override)
    return pathlib.Path.home() / ".cache/craftpipe/minecraft" / VERSION


def jar_path() -> pathlib.Path:
    return cache_dir() / "server.jar"


def _http(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "craftpipe-tests"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def server_download(fetch=_http) -> tuple[str, str]:
    """(url, sha1) of the server jar for VERSION, from Mojang's metadata."""
    manifest = json.loads(fetch(MANIFEST_URL))
    entry = next((v for v in manifest["versions"] if v["id"] == VERSION), None)
    if entry is None:
        raise RuntimeError(f"Mojang's version list has no {VERSION}")
    server = json.loads(fetch(entry["url"]))["downloads"]["server"]
    return server["url"], server["sha1"]


def expected_sha1(fetch=_http) -> str:
    return server_download(fetch)[1]


def verify(jar: pathlib.Path, sha1: str) -> bool:
    try:
        return hashlib.sha1(jar.read_bytes()).hexdigest() == sha1.strip().lower()
    except OSError:
        return False


def status() -> tuple[bool, str]:
    """(ready, message). The message names what is missing and how to fix it."""
    directory = cache_dir()
    jar, recorded = directory / "server.jar", directory / "server.jar.sha1"
    if not jar.exists() or not recorded.exists():
        return False, (f"the Minecraft {VERSION} server is not downloaded; run "
                       f"`{COMMAND} --accept-eula` (see the README)")
    if not verify(jar, recorded.read_text()):
        return False, (f"{jar} is corrupt or not the {VERSION} server; delete it and run "
                       f"`{COMMAND}` again")
    if not (directory / "eula-accepted").exists():
        return False, (f"the Minecraft EULA ({EULA_URL}) has not been accepted for the test "
                       f"server; if you accept it, run `{COMMAND} --accept-eula`")
    return True, f"Minecraft {VERSION} server ready in {directory}"


def main(argv=None, fetch=_http) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accept-eula", action="store_true",
                        help=f"record that you accept the Minecraft EULA ({EULA_URL})")
    args = parser.parse_args(argv)
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    jar, recorded = directory / "server.jar", directory / "server.jar.sha1"

    if not (jar.exists() and recorded.exists() and verify(jar, recorded.read_text())):
        url, sha1 = server_download(fetch)
        print(f"downloading Minecraft {VERSION} server from {url}")
        data = fetch(url)
        if hashlib.sha1(data).hexdigest() != sha1:
            print("error: the download does not match Mojang's checksum; nothing was kept",
                  file=sys.stderr)
            jar.unlink(missing_ok=True)
            return 1
        jar.write_bytes(data)
        recorded.write_text(sha1 + "\n")
    print(f"server jar verified: {jar}")

    if args.accept_eula:
        (directory / "eula-accepted").write_text(
            f"Minecraft EULA ({EULA_URL}) accepted for craftpipe's test server on "
            f"{datetime.date.today().isoformat()} by running {COMMAND} --accept-eula\n")
    ready, message = status()
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
