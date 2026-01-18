from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping


_DIRECTIVE_PREFIX = "-> "


@dataclass(frozen=True, slots=True)
class ReplyBuilder:
    """
    Builds reply attribute dictionaries from a reply definition.

    Supported directives (string values):
      - "-> fromPool"
      - "-> fromUuid"
      - "-> fromRequest.<Attr>"
      - "-> fromRequest.<Attr>.split('#')[5]"
      - "-> fromRequest.<Attr>.lower()"
      - "-> fromRequest.<Attr>.upper()"

    Any unsupported transform will produce a clean error.
    """

    pool: Any | None

    def build_attributes(
        self,
        request: Any,
        attributes: Mapping[str, Any],
        *,
        pool_exhausted_message: str = "IP Address in pool is exhausted",
    ) -> tuple[dict[str, Any], str | None]:
        """
        Returns (attribute_dict, error_message).

        If error_message is not None, attribute_dict will contain a single
        "Reply-Message" key (as expected by your tests).
        """
        result: dict[str, Any] = {}

        for attr_name, raw_value in attributes.items():
            value, err = self._resolve_value(request, attr_name, raw_value)
            if err is not None:
                if err == "pool_exhausted":
                    msg = pool_exhausted_message
                else:
                    msg = err
                return {"Reply-Message": msg}, msg
            result[attr_name] = value

        return result, None

    def _resolve_value(self, request: Any, attr_name: str, raw_value: Any) -> tuple[Any, str | None]:
        if isinstance(raw_value, str) and raw_value.startswith(_DIRECTIVE_PREFIX):
            directive = raw_value[len(_DIRECTIVE_PREFIX) :].strip()
            return self._apply_directive(request, attr_name, directive)
        return raw_value, None

    def _apply_directive(self, request: Any, attr_name: str, directive: str) -> tuple[Any, str | None]:
        if directive == "fromUuid":
            return str(uuid.uuid4()), None

        if directive == "fromPool":
            return self._from_pool(attr_name)

        if directive.startswith("fromRequest"):
            return self._from_request(request, directive)

        return None, f"unknown directive '{directive}'"

    def _from_pool(self, attr_name: str) -> tuple[Any, str | None]:
        if self.pool is None:
            return None, "pool missing"

        if attr_name == "Framed-IP-Address":
            value = self.pool.allocate_ipv4()
            return (None, "pool_exhausted") if value is None else (value, None)

        if attr_name == "Framed-IPv6-Prefix":
            value = self.pool.allocate_ipv6()
            return (None, "pool_exhausted") if value is None else (value, None)

        if attr_name == "Delegated-IPv6-Prefix":
            value = self.pool.allocate_ipv6_delegated()
            return (None, "pool_exhausted") if value is None else (value, None)

        return None, f"fromPool not supported for {attr_name}"

    def _from_request(self, request: Any, directive: str) -> tuple[Any, str | None]:
        """
        Parse: fromRequest.<Attr><optional transform>
        Example:
          fromRequest.User-Name
          fromRequest.User-Name.split('#')[5]
          fromRequest.User-Name.lower()
        """
        match = re.match(r"^fromRequest\.([A-Za-z0-9\-_]+)(.*)$", directive)
        if match is None:
            return None, f"invalid fromRequest directive '{directive}'"

        attr = match.group(1)
        suffix = match.group(2) or ""

        if attr not in request:
            return None, f"missing avp {attr} in incoming request"

        value = request[attr][0]
        try:
            transformed = _apply_safe_transform(str(value), suffix)
        except ValueError as exc:
            return None, str(exc)

        return transformed, None


_SPLIT_INDEX_RE = re.compile(
    r"""^\.split\((?P<q>['"])(?P<sep>.*?)(?P=q)\)\[(?P<idx>-?\d+)\]$"""
)
_LOWER_RE = re.compile(r"^\.lower\(\)$")
_UPPER_RE = re.compile(r"^\.upper\(\)$")


def _apply_safe_transform(value: str, suffix: str) -> str:
    """
    Allow a small, safe subset of the old eval()-based behaviour.
    """
    suffix = suffix.strip()
    if not suffix:
        return value

    if _LOWER_RE.fullmatch(suffix):
        return value.lower()

    if _UPPER_RE.fullmatch(suffix):
        return value.upper()

    m = _SPLIT_INDEX_RE.fullmatch(suffix)
    if m:
        sep = m.group("sep")
        idx = int(m.group("idx"))
        parts = value.split(sep)
        try:
            return parts[idx]
        except IndexError as exc:
            raise ValueError(f"split index out of range for value '{value}'") from exc

    raise ValueError(f"unsupported transform '{suffix}' (eval is disabled)")
