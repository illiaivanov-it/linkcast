"""HTTP server: viewer page, /viewer-config.js, /check, /token-check, /ping
and the MJPEG /stream.

Request logging never prints a full session code or token. Every log line is
scrubbed (see ``scrub_log_text``) so only ``redact_code`` output can appear.
"""

import json
import logging
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from host import config
from host.capture import FrameHub
from host.session import Session, authorize_token, exchange_code, redact_code

log = logging.getLogger("linkcast.http")

VIEWER_DIR = (Path(__file__).resolve().parent.parent / "viewer").resolve()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}

BOUNDARY = "frame"
_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
)
_CODE_IN_TEXT = re.compile(r"((?:code|token)=)([^&\s'\"]*)")


def scrub_log_text(text: str) -> str:
    """Redact ``code=`` / ``token=`` values to their first 2 chars plus ``***``."""
    return _CODE_IN_TEXT.sub(
        lambda m: m.group(1) + redact_code(m.group(2)) + "***", text
    )


def resolve_static(url_path: str) -> Path | None:
    """Map a URL path to a file inside viewer/, or None. Blocks path traversal."""
    relative = unquote(url_path).lstrip("/") or "index.html"
    if "\x00" in relative or "\\" in relative or ":" in relative:
        return None
    candidate = (VIEWER_DIR / relative).resolve()
    if not candidate.is_relative_to(VIEWER_DIR) or not candidate.is_file():
        return None
    return candidate


class LinkCastServer(ThreadingHTTPServer):
    # One thread per request; daemon threads so a never-ending stream handler
    # cannot keep the process alive on shutdown.
    daemon_threads = True

    # On Windows SO_REUSEADDR (which allow_reuse_address enables) lets a second
    # process bind the SAME port as a running one, silently splitting traffic
    # or hijacking it. Windows does not need it to restart quickly. On other
    # systems it is the normal, safe way to avoid "address already in use".
    allow_reuse_address = os.name != "nt"

    def __init__(self, address: tuple[str, int], session: Session, hub: FrameHub):
        self.session = session
        self.hub = hub
        super().__init__(address, Handler)

    def handle_error(self, request, client_address) -> None:
        if isinstance(sys.exc_info()[1], _DISCONNECT_ERRORS):
            return  # viewer went away; nothing to report
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    server: LinkCastServer
    server_version = "LinkCast"
    # Socket timeout so a stalled viewer cannot hold a thread forever.
    timeout = 15

    def log_message(self, format, *args) -> None:  # noqa: A002
        # Every log line in BaseHTTPRequestHandler (requests, errors) funnels
        # through here, and the request line contains "?code=...". Scrub it.
        log.info("%s - %s", self.client_address[0], scrub_log_text(format % args))

    # --- routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if parts.path == "/check":
            # The ONLY place a code is accepted; a good code returns a token.
            status, body = exchange_code(self.server.session, parts.query)
            self._send_text(status, body)
        elif parts.path == "/token-check":
            # Reconnect pre-check: 200 if the token is known, else 403.
            status, body = authorize_token(self.server.session, parts.query)
            self._send_text(status, body)
        elif parts.path == "/viewer-config.js":
            self._handle_viewer_config()
        elif parts.path == "/ping":
            # Code-free liveness probe for the viewer's watchdog. It must not
            # check the code, or an expired code would make a running viewer
            # think it was rejected.
            self._send_text(200, "ok")
        elif parts.path == "/stream":
            self._handle_stream(parts.query)
        else:
            self._handle_static(parts.path)

    # --- handlers ----------------------------------------------------------

    def _handle_viewer_config(self) -> None:
        settings = {
            "stallMinLoads": config.VIEWER_STALL_MIN_LOADS,
            "stallTimeoutMs": config.VIEWER_STALL_TIMEOUT_MS,
        }
        body = f"var LINKCAST_CONFIG = {json.dumps(settings)};".encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle_static(self, url_path: str) -> None:
        target = resolve_static(url_path)
        content_type = CONTENT_TYPES.get(target.suffix.lower()) if target else None
        if target is None or content_type is None:
            self._send_text(404, "Not found.")
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _handle_stream(self, query: str) -> None:
        # Needs a known token (not a code). Code expiry is irrelevant here, and
        # once open the stream runs until the viewer leaves or the agent stops.
        status, message = authorize_token(self.server.session, query)
        if status != 200:
            self._send_text(status, message)
            return
        hub = self.server.hub
        self.send_response(200)
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
        )
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        seq = 0
        try:
            while not hub.closed:
                item = hub.wait_next(seq, timeout=1.0)
                if item is None:
                    continue  # timeout (or shutdown): re-check hub.closed
                seq, jpeg = item
                header = (
                    f"--{BOUNDARY}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(jpeg)}\r\n\r\n"
                ).encode("ascii")
                self.wfile.write(header + jpeg + b"\r\n")
                self.wfile.flush()
        except _DISCONNECT_ERRORS:
            pass  # viewer closed the page or lost the network

    # --- helpers -----------------------------------------------------------

    def _send_text(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
