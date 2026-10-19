"""The request-log scrubber must never let a full code through."""

from host.server import resolve_static, scrub_log_text


def test_scrub_removes_full_code_from_request_line():
    line = '"GET /stream?code=482917&t=17 HTTP/1.1" 200 -'
    scrubbed = scrub_log_text(line)
    assert "482917" not in scrubbed
    assert "code=48***" in scrubbed
    assert "&t=17" in scrubbed


def test_scrub_handles_text_without_code():
    assert scrub_log_text("GET / HTTP/1.1") == "GET / HTTP/1.1"


def test_static_blocks_path_traversal():
    for path in (
        "/../host/config.py",
        "/..%2fhost/config.py",
        "/%2e%2e/host/session.py",
        r"/..\host\config.py",
        "/C:/Windows/win.ini",
    ):
        assert resolve_static(path) is None


def test_static_serves_viewer_index():
    assert resolve_static("/").name == "index.html"
    assert resolve_static("/viewer.js").name == "viewer.js"


def test_scrub_redacts_token():
    line = '"GET /stream?token=AbCdEfGhIjKlMnOp&t=1 HTTP/1.1" 200 -'
    scrubbed = scrub_log_text(line)
    assert "AbCdEfGhIjKlMnOp" not in scrubbed
    assert "token=Ab***" in scrubbed
