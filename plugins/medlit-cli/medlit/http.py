"""HTTP helpers with explicit failure classification."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import tempfile
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class NetworkBlockedError(RuntimeError):
    """Raised when network access is unavailable or repeatedly fails."""


class ApiError(RuntimeError):
    """Raised for non-recoverable remote API errors."""


_SSL_CONTEXT: ssl.SSLContext | None = None
_RATE_LOCK = threading.Lock()
_LAST_REQUEST: dict[str, float] = {}


def _pace_request(url: str) -> None:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.endswith("ncbi.nlm.nih.gov"):
        bucket, gap = "ncbi", (0.11 if os.environ.get("NCBI_API_KEY") else 0.35)
    elif host.endswith("europepmc.org") or host == "www.ebi.ac.uk":
        bucket, gap = "europepmc", 1.0
    else:
        return
    with _RATE_LOCK:
        delay = gap - (time.monotonic() - _LAST_REQUEST.get(bucket, 0.0))
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST[bucket] = time.monotonic()


@dataclass
class HttpClient:
    timeout: int = 30
    retries: int = 1
    sleep_seconds: float = 0.35
    cache_dir: Path | None = None

    def __post_init__(self):
        if self.cache_dir is None:
            cache_env = os.environ.get("MEDLIT_CACHE_DIR")
            if cache_env:
                self.cache_dir = Path(cache_env).expanduser().resolve()
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        return self.get_bytes(url, headers=headers).decode("utf-8", errors="replace")

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        cache_path = self._cache_path(url)
        if cache_path is not None and cache_path.exists():
            return cache_path.read_bytes()

        data = self._fetch(url, headers=headers)

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=cache_path.name, suffix=".tmp", dir=str(cache_path.parent))
            try:
                _pace_request(url)
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(data)
                Path(tmp_name).replace(cache_path)
            finally:
                if Path(tmp_name).exists():
                    Path(tmp_name).unlink()

        return data

    def _fetch(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        last_error = ""
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(self.sleep_seconds * attempt)
            try:
                req = urllib.request.Request(url, headers=headers or {})
                with urllib.request.urlopen(req, timeout=self.timeout, context=ssl_context()) as resp:
                    status = getattr(resp, "status", 200)
                    if status >= 400:
                        raise ApiError(f"HTTP {status}: {url}")
                    return resp.read()
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(5 if exc.code == 429 else self.sleep_seconds)
                    continue
                raise ApiError(f"HTTP {exc.code}: {body}") from exc
            except urllib.error.URLError as exc:
                last_error = str(getattr(exc, "reason", exc))
            except TimeoutError as exc:
                last_error = str(exc)
        raise NetworkBlockedError(last_error or f"Network request failed: {url}")

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        text = self.get_text(url, headers=headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ApiError(f"Could not parse JSON from {url}") from exc

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        bucket = _cache_bucket_for(url)
        normalized = _normalize_url_for_cache(url)
        key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return self.cache_dir / bucket / f"{key}.bin"


def _cache_bucket_for(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    path = urllib.parse.urlparse(url).path.lower()
    if host.endswith("ncbi.nlm.nih.gov") or host.endswith("nih.gov"):
        if "/esearch.fcgi" in path:
            return "pubmed_search"
        if "/efetch.fcgi" in path:
            return "pubmed_records"
        if "idconv" in path or "/pmc/utils/" in path:
            return "pmc_idconv"
        return "ncbi_other"
    if "europepmc.org" in host:
        return "europe_pmc"
    if "unpaywall.org" in host or "api.unpaywall.org" in host:
        return "unpaywall"
    return "other"


def _normalize_url_for_cache(url: str) -> str:
    """Remove identity parameters so identical queries share a cache entry."""
    parsed = urllib.parse.urlparse(url)
    query_parts = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    identity_params = {"api_key", "email", "tool", "app_key", "app_id"}
    filtered = [(k, v) for k, v in query_parts if k.lower() not in identity_params]
    normalized_query = urllib.parse.urlencode(filtered)
    return urllib.parse.urlunparse(parsed._replace(query=normalized_query))


def urlencode(params: dict[str, Any]) -> str:
    return urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def ssl_context() -> ssl.SSLContext:
    """Return an HTTPS context that works with common Windows proxy setups.

    Python's OpenSSL verifier does not automatically trust the Windows root
    store. Many VPN/proxy tools install their local CA into Windows, so we
    merge those certificates into a temporary CA bundle instead of disabling
    certificate verification.
    """

    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT

    if os.environ.get("MEDLIT_SSL_VERIFY", "").lower() in {"0", "false", "no"}:
        _SSL_CONTEXT = ssl._create_unverified_context()
        return _SSL_CONTEXT

    cafile = (
        os.environ.get("MEDLIT_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
    )
    if cafile:
        _SSL_CONTEXT = ssl.create_default_context(cafile=cafile)
        return _SSL_CONTEXT

    bundle = _build_ca_bundle()
    _SSL_CONTEXT = ssl.create_default_context(cafile=str(bundle) if bundle else None)
    return _SSL_CONTEXT


def _build_ca_bundle() -> Path | None:
    chunks: list[str] = []
    try:
        import certifi

        chunks.append(Path(certifi.where()).read_text(encoding="ascii", errors="ignore"))
    except Exception:
        pass

    if sys.platform.startswith("win") and hasattr(ssl, "enum_certificates"):
        for store_name in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, trust in ssl.enum_certificates(store_name):
                    if encoding == "x509_asn":
                        chunks.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                    elif encoding == "x509":
                        chunks.append(cert_bytes.decode("ascii", errors="ignore"))
            except Exception:
                continue

    if not chunks:
        return None

    path = Path(tempfile.gettempdir()) / "medlit_ca_bundle.pem"
    path.write_text("\n".join(chunks), encoding="ascii", errors="ignore")
    return path


def ncbi_identity() -> dict[str, str]:
    email = os.environ.get("MEDLIT_EMAIL") or os.environ.get("NCBI_EMAIL") or "noreply@example.com"
    tool = os.environ.get("MEDLIT_TOOL") or "medlit-cli"
    out = {"tool": tool, "email": email}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        out["api_key"] = api_key
    return out
