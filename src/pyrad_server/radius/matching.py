from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


PredicateRule = Mapping[str, str]
RuleGroup = Mapping[str, Sequence[PredicateRule]]
RuleSet = Sequence[RuleGroup]


@dataclass(frozen=True, slots=True)
class MatchEngine:
    """
    Selects pool and reply targets based on regex rules.

    Rules format (same as your config):
      - pool_match_rules: [ { "<pool>": [ { "<Attr>": "<regex>" }, ... ] }, ... ]
      - reply_match_rules_auth/acct: same structure as pool rules

    Semantics:
      - rules are evaluated in order (first match wins)
      - a target with an empty rule list is a catch-all and matches immediately
      - each rule is an AND across its attribute patterns
      - uses re.search(pattern, str(value))
    """

    pool_match_rules: RuleSet
    reply_match_rules_auth: RuleSet
    reply_match_rules_acct: RuleSet

    def select_pool(self, request: Any, default: str = "default") -> str:
        return match_rules(self.pool_match_rules, request, default=default)

    def select_reply(self, category: str, request: Any, default: str = "default") -> str:
        if category == "auth":
            rules = self.reply_match_rules_auth
        elif category == "acct":
            rules = self.reply_match_rules_acct
        else:
            raise ValueError(f"Unknown reply category: {category!r}")
        return match_rules(rules, request, default=default)


def match_rules(rules: RuleSet, request: Any, *, default: str) -> str:
    """
    Evaluate an ordered ruleset and return the first matching target.
    """
    for group in rules:
        target, predicates = _unpack_group(group)

        # catch-all: "<target>: []"
        if not predicates:
            return target

        for predicate in predicates:
            if rule_matches(predicate, request):
                return target

    return default


def rule_matches(rule: PredicateRule, request: Any) -> bool:
    """
    A rule matches if all (attribute, regex) pairs match.
    """
    for attr, pattern in rule.items():
        value = _first_attr_value(request, attr)
        if value is None:
            return False
        if re.search(pattern, str(value)) is None:
            return False
    return True


def _unpack_group(group: RuleGroup) -> tuple[str, Sequence[PredicateRule]]:
    """
    A group is expected to be a single-key mapping: {"target": [ {..}, {..} ] }
    """
    if not group:
        raise ValueError("Rule group must not be empty")

    if len(group) != 1:
        raise ValueError(f"Rule group must have exactly one target key, got {len(group)} keys")

    target = next(iter(group.keys()))
    predicates = group[target]
    return str(target), predicates


def _first_attr_value(request: Any, attr: str) -> Any | None:
    """
    Compatible with pyrad packet interface:
      - `attr in request` is supported
      - `request[attr]` returns a list-like of values
    Also works for simple dicts where value is a list.
    """
    try:
        if attr not in request:
            return None
        values = request[attr]
    except Exception:
        return None

    if not values:
        return None

    try:
        return values[0]
    except Exception:
        return None
