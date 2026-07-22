#!/usr/bin/env python3
"""Install yt-dlp with a BENIGN cookies.py, so nothing an EDR flags is ever written.

Why: yt-dlp's real yt_dlp/cookies.py contains browser-cookie extraction (Chrome/Firefox
+ OS keyring decryption) — a legitimate infostealer-class capability that endpoint
security (e.g. SentinelOne) quarantines on write, breaking the install.

We don't need that capability to download public audio. This script downloads the wheel,
rewrites it *in memory* replacing cookies.py with a stub that has NO browser/keyring
access (empty, file-only cookie jar), fixes the wheel RECORD hash, and installs it.
The flagged code never touches the filesystem, so no detection fires.

This does NOT disable or bypass your security tool — it installs a build without the
flagged feature. On a managed corporate device, prefer an IT-approved exclusion instead.

Usage:  python3 tools/install_ytdlp_stub.py
"""
import base64
import glob
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile

STUB = '''\
"""Benign stand-in for yt_dlp/cookies.py.

Provides only the symbols yt-dlp imports. Browser/keyring cookie extraction is
intentionally NOT implemented (that is the capability endpoint security flags).
Public downloads work; --cookies-from-browser is disabled by design.
"""
import http.cookiejar
import http.cookies
import urllib.request

SUPPORTED_BROWSERS = []
SUPPORTED_KEYRINGS = []


class CookieLoadError(Exception):
    pass


class LenientSimpleCookie(http.cookies.SimpleCookie):
    """Tolerate malformed cookies instead of raising."""

    def load(self, data):
        try:
            return super().load(data)
        except http.cookies.CookieError:
            return None


class YoutubeDLCookieJar(http.cookiejar.MozillaCookieJar):
    """Empty / cookies.txt-only jar. No browser or keyring access."""

    _HTTPONLY_PREFIX = "#HttpOnly_"

    def get_cookie_header(self, url):
        req = urllib.request.Request(url)
        self.add_cookie_header(req)
        return req.get_header("Cookie")

    def get_cookies_for_url(self, url):
        try:
            req = urllib.request.Request(url)
            return self._cookies_for_request(req)
        except Exception:
            return []


def load_cookies(cookie_file, browser_specification, ydl):
    """Return a cookie jar. Browser extraction is disabled; cookie files still work."""
    jar = YoutubeDLCookieJar()
    if browser_specification is not None:
        raise CookieLoadError(
            "browser cookie extraction is disabled in this build "
            "(cookies.py stub). Use --cookies <file> instead."
        )
    if cookie_file is not None:
        cookie_file = os.path.expanduser(cookie_file)
        if os.path.isfile(cookie_file):
            jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    return jar


import os  # noqa: E402  (used by load_cookies)
'''


def record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def main():
    tmp = tempfile.mkdtemp(prefix="ytdlp_stub_")
    print("downloading yt-dlp wheel …")
    subprocess.check_call([sys.executable, "-m", "pip", "download", "yt-dlp",
                           "--no-deps", "-d", tmp])
    wheels = glob.glob(os.path.join(tmp, "yt_dlp-*.whl"))
    if not wheels:
        sys.exit("no wheel downloaded (yt-dlp may only ship an sdist for this Python)")
    src = wheels[0]
    out_dir = tempfile.mkdtemp(prefix="ytdlp_patched_")
    dst = os.path.join(out_dir, os.path.basename(src))
    stub_bytes = STUB.encode()
    print(f"patching {os.path.basename(src)} (cookies.py -> benign stub) …")

    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        record = next((n for n in names if n.endswith(".dist-info/RECORD")), None)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                data = zin.read(n)
                if n.endswith("yt_dlp/cookies.py"):
                    data = stub_bytes           # flagged bytes never written to disk
                elif n == record:
                    lines = []
                    for line in data.decode().splitlines():
                        if line.startswith("yt_dlp/cookies.py,"):
                            line = f"yt_dlp/cookies.py,{record_hash(stub_bytes)},{len(stub_bytes)}"
                        lines.append(line)
                    data = ("\n".join(lines) + "\n").encode()
                zout.writestr(n, data)

    print("installing patched wheel …")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--force-reinstall", "--no-deps", dst])
    print("\nverifying …")
    subprocess.check_call([sys.executable, "-c",
                           "import yt_dlp; from yt_dlp.cookies import YoutubeDLCookieJar; "
                           "print('yt-dlp', yt_dlp.version.__version__, 'OK (benign cookies stub)')"])


if __name__ == "__main__":
    main()
