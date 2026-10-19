"""Launch-flag parsing and banner lifetime wording."""

import pytest

from host import config
from host.__main__ import format_lifetime, parse_args


def test_default_ttl_comes_from_config():
    assert parse_args([]).code_ttl == config.CODE_LIFETIME_SECONDS


def test_ttl_flag():
    assert parse_args(["--code-ttl", "60"]).code_ttl == 60


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.5"])
def test_bad_ttl_rejected(bad):
    with pytest.raises(SystemExit):
        parse_args(["--code-ttl", bad])


def test_format_lifetime():
    assert format_lifetime(3600) == "60 minutes"
    assert format_lifetime(60) == "1 minute"
    assert format_lifetime(5) == "5 seconds"
    assert format_lifetime(90) == "90 seconds"
