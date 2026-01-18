from __future__ import annotations

from pyrad_server.radius.matching import MatchEngine


class FakeRequest(dict):
    """Mimics pyrad packet mapping: values are lists, e.g. {'User-Name': ['alice']}."""


def test_select_pool_match_found() -> None:
    engine = MatchEngine(
        pool_match_rules=[{"pool1": [{"User-Name": "ali"}]}],  # re.search -> substring ok
        reply_match_rules_auth=[],
        reply_match_rules_acct=[],
    )
    req = FakeRequest({"User-Name": ["alice"]})
    assert engine.select_pool(req, default="default") == "pool1"


def test_select_pool_default_when_no_match() -> None:
    engine = MatchEngine(
        pool_match_rules=[{"pool1": [{"User-Name": "bob"}]}],
        reply_match_rules_auth=[],
        reply_match_rules_acct=[],
    )
    req = FakeRequest({"User-Name": ["alice"]})
    assert engine.select_pool(req, default="default") == "default"


def test_select_pool_catch_all_empty_rule_list() -> None:
    engine = MatchEngine(
        pool_match_rules=[{"pool1": []}],  # catch-all
        reply_match_rules_auth=[],
        reply_match_rules_acct=[],
    )
    req = FakeRequest({"User-Name": ["anything"]})
    assert engine.select_pool(req, default="default") == "pool1"


def test_select_reply_auth_and_acct() -> None:
    engine = MatchEngine(
        pool_match_rules=[],
        reply_match_rules_auth=[{"ok": [{"User-Name": "alice"}]}],
        reply_match_rules_acct=[{"acct_ok": [{"User-Name": "alice"}]}],
    )
    req = FakeRequest({"User-Name": ["alice"]})
    assert engine.select_reply("auth", req, default="default") == "ok"
    assert engine.select_reply("acct", req, default="default") == "acct_ok"
