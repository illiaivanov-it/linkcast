"""Unit tests for session code handling. No screen, no network."""

from host import config
from host.session import (
    Session,
    Verdict,
    authorize_token,
    exchange_code,
    generate_code,
    normalize_code,
    redact_code,
    spaced,
)


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


# --- generation -------------------------------------------------------------


def test_code_has_configured_length_and_alphabet():
    for _ in range(200):
        code = generate_code()
        assert len(code) == config.CODE_LENGTH
        assert set(code) <= set(config.CODE_ALPHABET)


def test_codes_differ_between_calls():
    codes = {generate_code() for _ in range(50)}
    assert len(codes) > 40  # 10**6 space; collisions this frequent mean not random


def test_generation_uses_secrets(monkeypatch):
    calls = []

    def fake_choice(alphabet):
        calls.append(alphabet)
        return alphabet[0]

    monkeypatch.setattr("host.session.secrets.choice", fake_choice)
    assert generate_code(length=4, alphabet="XYZ") == "XXXX"
    assert len(calls) == 4


def test_normalize_strips_spaces_dashes_and_case():
    assert normalize_code(" 482-917 ") == "482917"
    assert normalize_code("4 8 2 9 1 7") == "482917"
    assert normalize_code("ab-cd") == "ABCD"


def test_spaced_for_reading_aloud():
    assert spaced("482917") == "4 8 2 9 1 7"


# --- expiry (injected clock, no sleeping) -----------------------------------


def test_code_valid_before_lifetime_and_invalid_after():
    clock = FakeClock()
    session = Session(code="123456", lifetime=3600, clock=clock)
    assert session.verify("123456") is Verdict.OK
    clock.now += 3599
    assert session.verify("123456") is Verdict.OK
    clock.now += 1
    assert session.is_expired()
    assert session.verify("123456") is Verdict.EXPIRED


def test_expiry_reported_through_exchange_code():
    clock = FakeClock()
    session = Session(code="123456", lifetime=60, clock=clock)
    clock.now += 61
    status, message = exchange_code(session, "code=123456")
    assert status == 403
    assert "expired" in message.lower()


# --- rejection path (/check via exchange_code, /stream via authorize_token) --


def test_valid_code_issues_token():
    session = Session(code="123456")
    status, token = exchange_code(session, "code=123456")
    assert status == 200
    assert len(token) >= 16
    assert authorize_token(session, "token=" + token) == (200, "OK")


def test_exchange_accepts_user_formatting():
    session = Session(code="123456")
    assert exchange_code(session, "code=123-456")[0] == 200
    assert exchange_code(session, "code=123%20456")[0] == 200


def test_exchange_rejects_missing_code():
    session = Session(code="123456")
    for query in ("", "t=1", "code=", "code=%20"):
        status, message = exchange_code(session, query)
        assert status == 403
        assert "no code" in message.lower()


def test_exchange_rejects_wrong_code():
    session = Session(code="123456")
    for query in ("code=000000", "code=12345", "code=1234567", "code=abc"):
        status, message = exchange_code(session, query)
        assert status == 403
        assert "not correct" in message.lower()


def test_exchange_handles_odd_input_without_raising():
    session = Session(code="123456")
    assert exchange_code(session, "code=%C3%A9%E2%82%AC")[0] == 403  # non-ASCII
    assert exchange_code(session, "code=" + "9" * 5000)[0] == 403
    assert exchange_code(session, "code=1&code=2")[0] == 403  # first value wins


def test_rejection_never_contains_the_code():
    session = Session(code="123456")
    for query in ("", "code=999999"):
        assert "123456" not in exchange_code(session, query)[1]


def test_session_repr_hides_code():
    assert "123456" not in repr(Session(code="123456"))


# --- logging helper ---------------------------------------------------------


def test_redact_code_keeps_at_most_two_characters():
    assert redact_code("482917") == "48"
    assert redact_code("4829171234567") == "48"
    assert redact_code("48") == ""
    assert redact_code("4") == ""
    assert redact_code("") == ""
    assert len(redact_code("anything long")) <= 2


# --- tokens: continuation credential ---------------------------------------


def test_token_still_works_after_code_expires():
    clock = FakeClock()
    session = Session(code="123456", lifetime=60, clock=clock)
    _, token = exchange_code(session, "code=123456")
    clock.now += 100_000
    assert session.is_expired()
    assert exchange_code(session, "code=123456")[0] == 403
    assert authorize_token(session, "token=" + token) == (200, "OK")


def test_unknown_or_missing_token_rejected():
    session = Session(code="123456")
    session.issue_token()
    for query in ("", "token=", "token=bogus", "code=123456", "t=1"):
        status, message = authorize_token(session, query)
        assert status == 403
        assert message != "OK"


def test_expired_code_issues_no_token():
    clock = FakeClock()
    session = Session(code="123456", lifetime=60, clock=clock)
    clock.now += 61
    status, body = exchange_code(session, "code=123456")
    assert status == 403
    assert authorize_token(session, "token=" + body)[0] == 403


def test_wrong_code_issues_no_token():
    session = Session(code="123456")
    status, body = exchange_code(session, "code=000000")
    assert status == 403
    assert authorize_token(session, "token=" + body)[0] == 403
    assert not session._tokens


def test_each_exchange_gives_distinct_token():
    session = Session(code="123456")
    tokens = {exchange_code(session, "code=123456")[1] for _ in range(20)}
    assert len(tokens) == 20


def test_code_is_not_accepted_as_a_token():
    session = Session(code="123456")
    assert authorize_token(session, "token=123456")[0] == 403


def test_new_session_does_not_know_old_tokens():
    old = Session(code="123456")
    _, token = exchange_code(old, "code=123456")
    restarted = Session(code="123456")
    assert authorize_token(restarted, "token=" + token)[0] == 403


def test_repr_hides_tokens():
    session = Session(code="123456")
    _, token = exchange_code(session, "code=123456")
    assert token not in repr(session)
