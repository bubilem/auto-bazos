"""Minimal robots.txt checker with wildcard support (urllib.robotparser ignores '*' inside paths,
and Bazoš disallows patterns like /*hledat=)."""
import re
from urllib.parse import urlsplit


def _pattern_to_regex(pattern):
    anchored = pattern.endswith("$")
    body = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if anchored else ""))


def parse_rules(text, user_agent):
    """Return [(is_allow, regex, length)] for the most specific matching group (our UA, else '*')."""
    groups = {}  # agent -> rules
    agents, in_rules = [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (p.strip() for p in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
            groups.setdefault(value.lower(), [])
        elif field in ("allow", "disallow"):
            in_rules = True
            if not value:
                continue  # empty Disallow = allow all
            for a in agents:
                groups[a].append((field == "allow", _pattern_to_regex(value), len(value)))
    ua = user_agent.lower()
    for agent, rules in groups.items():
        if agent != "*" and agent in ua:
            return rules
    return groups.get("*", [])


def is_allowed(rules, path_and_query):
    best = None  # (length, allow)
    for allow, rx, length in rules:
        if rx.match(path_and_query):
            if best is None or length > best[0] or (length == best[0] and allow):
                best = (length, allow)
    return True if best is None else best[1]


class RobotsCache:
    """Fetches and caches robots.txt per origin using a `fetch_text(url) -> str | None` callback."""

    def __init__(self, fetch_text, user_agent):
        self._fetch, self._ua, self._rules = fetch_text, user_agent, {}

    def allowed(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._rules:
            text = self._fetch(origin + "/robots.txt")
            self._rules[origin] = parse_rules(text, self._ua) if text else []
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        return is_allowed(self._rules[origin], target)
