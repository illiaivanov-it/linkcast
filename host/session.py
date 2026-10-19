"""Session code: generation, validation, expiry and log-safe redaction.

Two credentials with different jobs. The CODE is a short-lived entry pass that
can be read aloud; ``exchange_code`` trades a valid, unexpired code for a
random TOKEN. The token is the per-display continuation credential: it lets a
display reconnect by itself, keeps working after the code expires, and lives
until the agent stops. Nothing here ends a stream that is already running.
"""

import enum
import hmac
import secrets
import threading
import time
from collections.abc import Callable
from urllib.parse import parse_qs

from host import config

# Longest raw input we are willing to look at; anything longer cannot be a code.
_MAX_INPUT_LENGTH = 64


def generate_code(
    length: int = config.CODE_LENGTH, alphabet: str = config.CODE_ALPHABET
) -> str:
    """Return a random code drawn from ``alphabet`` using ``secrets``."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def normalize_code(raw: str) -> str:
    """Strip whitespace and dashes and upper-case, so "482-917" == "482917"."""
    cleaned = "".join(ch for ch in raw if not ch.isspace() and ch != "-")
    return cleaned.upper()


def redact_code(code: str) -> str:
    """Reduce a code to at most its first 2 characters, for logging.

    Use this for ANY log line that could contain a code taken from a request.
    Codes of 2 characters or fewer are returned as an empty string, so a short
    value can never be echoed back in full.
    """
    return code[:2] if len(code) > 2 else ""


def generate_token() -> str:
    """Return a new random continuation token (128 bits, URL-safe)."""
    return secrets.token_urlsafe(16)


def spaced(code: str) -> str:
    """Format a code to be read aloud: "482917" -> "4 8 2 9 1 7"."""
    return " ".join(code)


class Verdict(enum.Enum):
    OK = "ok"
    MISSING = "missing"
    WRONG = "wrong"
    EXPIRED = "expired"


class Session:
    """One code per agent run. Restarting the agent gives a new code."""

    def __init__(
        self,
        code: str | None = None,
        lifetime: float = config.CODE_LIFETIME_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._code = code if code is not None else generate_code()
        self._lifetime = lifetime
        self._clock = clock  # injectable so tests need not sleep
        self._issued_at = clock()
        # Continuation tokens: in memory only, valid until the agent stops.
        # They are deliberately NOT affected by code expiry.
        self._tokens: set[str] = set()
        self._token_lock = threading.Lock()

    def __repr__(self) -> str:
        return (
            "Session(code=<hidden>, tokens=<hidden>)"  # never leak the code into a log
        )

    @property
    def code(self) -> str:
        """The full code. Only the startup banner should print this."""
        return self._code

    @property
    def lifetime(self) -> float:
        return self._lifetime

    def is_expired(self) -> bool:
        return self._clock() - self._issued_at >= self._lifetime

    def issue_token(self) -> str:
        token = generate_token()
        with self._token_lock:
            self._tokens.add(token)
        return token

    def token_known(self, supplied: str | None) -> bool:
        if not supplied:
            return False
        # Tokens are random 128-bit values; a set lookup leaks nothing useful.
        with self._token_lock:
            return supplied in self._tokens

    def verify(self, supplied: str | None) -> Verdict:
        """Check a code supplied by a viewer that is making a NEW connection."""
        if supplied is None:
            return Verdict.MISSING
        candidate = normalize_code(supplied)
        if not candidate:
            return Verdict.MISSING
        if len(candidate) > _MAX_INPUT_LENGTH:
            return Verdict.WRONG
        # Compare as bytes: compare_digest raises TypeError on non-ASCII str.
        matches = hmac.compare_digest(
            candidate.encode("utf-8"), normalize_code(self._code).encode("utf-8")
        )
        if not matches:
            return Verdict.WRONG
        if self.is_expired():
            return Verdict.EXPIRED
        return Verdict.OK


_MESSAGES = {
    Verdict.OK: "OK",
    Verdict.MISSING: (
        "No code was given. Enter the code shown on the instructor's screen."
    ),
    Verdict.WRONG: "That code is not correct. Check the code and try again.",
    Verdict.EXPIRED: (
        "That code has expired. Ask the instructor to restart LinkCast for a new code."
    ),
}


def _first(query_string: str, name: str) -> str | None:
    values = parse_qs(query_string).get(name)
    return values[0] if values else None


def exchange_code(session: Session, query_string: str) -> tuple[int, str]:
    """Handle /check?code=...: trade a valid, unexpired code for a token.

    Returns ``(200, token)`` or ``(403, message)``. No token is issued for a
    missing, wrong or expired code. The code is the ENTRY pass; this is the
    only place it is accepted.
    """
    verdict = session.verify(_first(query_string, "code"))
    if verdict is Verdict.OK:
        return 200, session.issue_token()
    return 403, _MESSAGES[verdict]


def authorize_token(session: Session, query_string: str) -> tuple[int, str]:
    """Handle /stream and /token-check: is ``token=`` known to this run?

    Code expiry plays no part here: a token works as long as the agent runs.
    """
    if session.token_known(_first(query_string, "token")):
        return 200, "OK"
    return 403, _UNKNOWN_CONNECTION_MESSAGE


_UNKNOWN_CONNECTION_MESSAGE = (
    "This connection is not recognised (the host may have been restarted). "
    "Enter the code shown on the instructor's screen."
)
