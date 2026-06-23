from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "yclid",
    "mc_cid",
    "mc_eid",
}
COMMON_HOST_PREFIXES = ("www.", "m.", "sp.")


def normalize_url(raw_url: str) -> str:
    """Return a stable URL key for de-duplication and external handoff."""
    split = urlsplit(raw_url.strip())
    scheme = (split.scheme or "https").lower()
    netloc = split.netloc.lower()
    path = split.path or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if not _is_tracking_key(key)
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_domain(raw_url_or_domain: str) -> str:
    """Normalize a URL or hostname into a comparable domain string."""
    candidate = raw_url_or_domain.strip()
    split = urlsplit(candidate if "://" in candidate else f"https://{candidate}")
    host = (split.netloc or split.path).lower().split("@")[-1].split(":")[0]
    for prefix in COMMON_HOST_PREFIXES:
        if host.startswith(prefix):
            return host[len(prefix) :]
    return host


def _is_tracking_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_QUERY_KEYS or lowered.startswith(TRACKING_QUERY_PREFIXES)
