"""SSRF-safe загрузка URL: резолв → проверка IP → TCP-коннект на проверенный IP.

Публичный контракт: `fetch_text(url, *, max_bytes, max_chars, timeout)` →
`(text, title)`; ошибки — `HttpFetchError` с HTTP-статусом для API (`422`/`413`).
Редиректы не читаются автоматически: каждый хоп проверяется и резолвится заново,
поэтому rebinding-окно в редиректе не превращается в обход allowlist.
"""
from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

from .knowledge.extract import normalize_body

REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
CONTENT_TYPES = frozenset({"text/html", "text/plain", "application/xhtml+xml"})
MAX_REDIRECTS = 3
# NAT64 / IPv4-compatible адреса: `is_global` их пропускает, но по факту
# это упаковка внутреннего IPv4 (например, `64:ff9b::7f00:1` = 127.0.0.1).
# Плюс multicast и IETF-assignments (192.0.0.0/24) — не HTTP-назначение.
BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "::/96",
        "224.0.0.0/4",
        "ff00::/8",
        "192.0.0.0/24",
    )
)
SKIP_TAGS = {"script", "style", "noscript", "template"}
BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header",
    "footer", "blockquote", "pre", "hr",
}


class HttpFetchError(Exception):
    """Сбой загрузки URL; `status_code` — код HTTP-ответа API."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _PinnedBackend(httpcore.SyncBackend):
    """TCP только на проверенные IP; Host/SNI остаются исходными (их даёт httpcore)."""

    def __init__(self, ips: list[str]) -> None:
        self._ips = ips

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        error: Exception | None = None
        for ip in self._ips:
            try:
                return super().connect_tcp(
                    ip,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                error = exc
        raise error or httpcore.ConnectError("no resolved address")


class PinnedTransport(httpx.HTTPTransport):
    """httpx-транспорт поверх пула, который коннектится на проверенные IP.

    Пул ключуется исходным origin из URL, поэтому в TLS уходит исходный
    `server_hostname`, а `Host` формируется httpx из URL — не из IP.
    """

    def __init__(self, ips: list[str]) -> None:
        super().__init__()
        self._pool = httpcore.ConnectionPool(network_backend=_PinnedBackend(ips))


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
        else:
            self.parts.append(data)


def _html_to_text(html: str) -> tuple[str, str]:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    text = normalize_body("".join(parser.parts))
    return text, " ".join(parser.title.split())


def _blocked(address) -> bool:
    """Приватный/служебный адрес, multicast или NAT64/IPv4-compatible."""
    if not address.is_global:
        return True
    return any(address in network for network in BLOCKED_NETWORKS)


def _public_ips(host: str, port: int) -> list[str]:
    """Все IP хоста — публичные (не private/loopback/link-local/reserved)."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise HttpFetchError(422, "url host cannot be resolved") from exc
    ips: list[str] = []
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError as exc:
            raise HttpFetchError(422, "url host cannot be resolved") from exc
        if _blocked(address):
            raise HttpFetchError(422, "url points to a private address")
        if address.compressed not in ips:
            ips.append(address.compressed)
    if not ips:
        raise HttpFetchError(422, "url host cannot be resolved")
    return ips


def _check_url(url: str) -> list[str]:
    """Схема/host/port и публичность всех адресов — до сетевого запроса."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise HttpFetchError(422, "only http/https urls are supported")
    if not parts.hostname:
        raise HttpFetchError(422, "url has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise HttpFetchError(422, "url has invalid port") from exc
    return _public_ips(parts.hostname, port)


def _fetch_once(
    url: str, *, max_bytes: int, timeout: float
) -> tuple[int, str | None, str]:
    """Один запрос без редиректов → (статус, location, сырой текст).

    Коннект идёт на IP из `_check_url`, тело читается потоком с лимитом
    `max_bytes`, тип содержимого — только текстовый allowlist.
    """
    try:
        with httpx.Client(
            transport=PinnedTransport(_check_url(url)),
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            with client.stream("GET", url) as response:
                status = response.status_code
                location = response.headers.get("location")
                if status in REDIRECT_CODES or status >= 400:
                    return status, location, ""
                content_type = (
                    (response.headers.get("content-type") or "").split(";")[0]
                    .strip()
                    .lower()
                )
                if content_type not in CONTENT_TYPES:
                    raise HttpFetchError(422, "url content type is not supported")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise HttpFetchError(
                            413, f"url content exceeds {max_bytes} bytes"
                        )
                encoding = response.encoding or "utf-8"
                try:
                    text = body.decode(encoding, errors="replace")
                except LookupError:
                    # Неизвестный charset в заголовке — не 500: читаем как utf-8.
                    text = body.decode("utf-8", errors="replace")
                return status, location, text
    except httpx.HTTPError as exc:
        raise HttpFetchError(422, "url fetch failed") from exc


def fetch_text(
    url: str, *, max_bytes: int, max_chars: int, timeout: float
) -> tuple[str, str]:
    """Скачать URL → (текст, title); каждый редирект проверяется отдельно."""
    for _ in range(MAX_REDIRECTS + 1):
        status, location, raw = _fetch_once(
            url, max_bytes=max_bytes, timeout=timeout
        )
        if status in REDIRECT_CODES:
            if not location:
                raise HttpFetchError(422, "url redirect without location")
            url = urljoin(url, location)
            continue
        if status >= 400:
            raise HttpFetchError(422, f"url returned {status}")
        return _html_to_text(raw[:max_chars])
    raise HttpFetchError(422, "too many redirects")
