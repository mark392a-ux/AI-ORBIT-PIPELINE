"""
URL normalization.

Goal: two URLs that point at the "same" resource should normalize to an
identical string, so entity resolution's URL-matching signal is reliable.

Rules applied:
1. Lowercase scheme + host (paths stay case-sensitive — GitHub repo paths
   are case-sensitive).
2. Strip default ports (:80 for http, :443 for https).
3. Strip trailing slash (except bare domain root).
4. Drop known-noise query params (utm_*, ref, fbclid, gclid, etc.).
5. Sort remaining query params for determinism.
6. Force https where the host is known to always redirect (github.com,
   huggingface.co) to avoid http/https duplicate URLs.
7. Remove URL fragments (#section) since they rarely change identity.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_NOISE_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "ref_src", "fbclid", "gclid", "mc_cid", "mc_eid", "igshid",
    "si",  # youtube share param
}

_FORCE_HTTPS_HOSTS = {"github.com", "huggingface.co", "youtube.com", "www.youtube.com"}


def normalize_url(raw_url: str) -> str:
    if not raw_url:
        return raw_url

    raw_url = raw_url.strip()
    parts = urlsplit(raw_url)

    scheme = parts.scheme.lower() or "https"
    host = parts.netloc.lower()

    # Strip default ports.
    if host.endswith(":80") and scheme == "http":
        host = host[: -len(":80")]
    if host.endswith(":443") and scheme == "https":
        host = host[: -len(":443")]

    if host in _FORCE_HTTPS_HOSTS:
        scheme = "https"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _NOISE_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)

    # Drop fragment entirely.
    normalized = urlunsplit((scheme, host, path, query, ""))
    return normalized
