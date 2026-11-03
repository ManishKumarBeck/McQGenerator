"""Download a web page or online document safely.

Guards against server-side request forgery: only http(s), no credentials in the URL, every
redirect hop is re-validated, and hosts resolving to private, loopback, link-local or other
non-public addresses are refused (unless ALLOW_PRIVATE_URLS is enabled for local testing).
"""

import ipaddress
import socket
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from ...errors import InvalidInputError

MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; McqGen/1.0; +https://github.com/)"

CONTENT_TYPES = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "application/pdf": "pdf",
    "application/epub+zip": "epub",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


@dataclass
class FetchedDocument:
    url: str
    data: bytes
    file_type: str


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidInputError("Enter a full web address starting with http:// or https://.")
    if parts.username or parts.password:
        raise InvalidInputError("Links containing a username or password are not allowed.")
    if len(url) > 2000:
        raise InvalidInputError("That link is too long.")
    return url


def _is_private_literal(hostname: str) -> bool:
    host = hostname.strip("[]").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _uses_proxy(scheme: str, hostname: str) -> bool:
    proxies = urllib.request.getproxies()
    return bool(proxies.get(scheme) or proxies.get("all")) and not urllib.request.proxy_bypass(hostname)


def _check_host(hostname: str, port: int | None, scheme: str) -> None:
    if _is_private_literal(hostname):
        raise InvalidInputError("Links to private or local network addresses are not allowed.")
    try:
        infos = socket.getaddrinfo(hostname, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        # Behind an HTTP proxy the proxy resolves names, so local DNS may legitimately fail.
        if _uses_proxy(scheme, hostname):
            return
        raise InvalidInputError(f"Couldn't find the website “{hostname}”. Check the link.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise InvalidInputError("Links to private or local network addresses are not allowed.")


def _file_type(content_type: str, url: str) -> str:
    media = content_type.split(";")[0].strip().lower()
    if media in CONTENT_TYPES:
        return CONTENT_TYPES[media]
    path = urlsplit(url).path.lower()
    for suffix, kind in (
        (".pdf", "pdf"),
        (".epub", "epub"),
        (".docx", "docx"),
        (".md", "md"),
        (".txt", "txt"),
    ):
        if path.endswith(suffix):
            return kind
    if media in ("application/octet-stream", ""):
        return "html"
    raise InvalidInputError(f"This link points to an unsupported kind of file ({media}).")


def fetch_document(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    allow_private: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> FetchedDocument:
    url = validate_url(url)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain,*/*;q=0.8"},
        transport=transport,
    ) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if not allow_private:
                _check_host(parts.hostname or "", parts.port, parts.scheme)
            try:
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise InvalidInputError("The website returned a broken redirect.")
                        url = validate_url(urljoin(url, location))
                        continue
                    if response.status_code >= 400:
                        raise InvalidInputError(
                            f"The website returned an error (HTTP {response.status_code}). "
                            "The page may be private, removed or blocking automated access."
                        )
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise InvalidInputError(_too_large(max_bytes))
                    data = bytearray()
                    for block in response.iter_bytes():
                        data.extend(block)
                        if len(data) > max_bytes:
                            raise InvalidInputError(_too_large(max_bytes))
                    file_type = _file_type(response.headers.get("content-type", ""), url)
                    return FetchedDocument(url=str(response.url), data=bytes(data), file_type=file_type)
            except httpx.TimeoutException as exc:
                raise InvalidInputError("The website took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise InvalidInputError(
                    "Couldn't download the link. Check the address and your connection."
                ) from exc
    raise InvalidInputError("The link redirected too many times.")


def _too_large(max_bytes: int) -> str:
    return f"The linked document is larger than {max_bytes / (1024 * 1024):g} MB."
