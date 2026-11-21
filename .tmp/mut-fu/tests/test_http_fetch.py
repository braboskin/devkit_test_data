"""WS-B2: F1 SSRF-pinning загрузки URL (F3-лимит тела — в tests/test_documents)."""
from __future__ import annotations

import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest import mock

import httpcore
import httpx

from app.backend import http_fetch

PAGE = (
    "<html><head><title>Статья про бюджет</title></head><body>"
    "<script>var hidden = 1;</script>"
    "<h1>Заголовок</h1><p>Иван Петров обсудил бюджет.</p></body></html>"
)
BIG_PAGE = "<html><body><p>" + "слово " * 200 + "</p></body></html>"


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.0: соединение закрывается после ответа — без keep-alive шума при stop.
    protocol_version = "HTTP/1.0"

    def log_message(self, *args) -> None:  # noqa: D102 — тишина в тестах
        pass

    def _send(self, status: int, body: bytes, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — имя задано stdlib
        self.server.requests.append(
            (self.path, self.headers.get("host"))
        )
        if self.path == "/page":
            self._send(
                200,
                PAGE.encode("utf-8"),
                {"Content-Type": "text/html; charset=utf-8"},
            )
        elif self.path == "/plain":
            self._send(200, b"hello plain", {"Content-Type": "text/plain"})
        elif self.path == "/pdf":
            self._send(200, b"%PDF-1.7", {"Content-Type": "application/pdf"})
        elif self.path == "/big":
            self._send(
                200, b"x" * 4096, {"Content-Type": "text/html"}
            )
        elif self.path == "/long":
            self._send(
                200,
                BIG_PAGE.encode("utf-8"),
                {"Content-Type": "text/html; charset=utf-8"},
            )
        elif self.path == "/missing":
            self._send(404, b"not found", {"Content-Type": "text/html"})
        elif self.path == "/badcharset":
            self._send(
                200,
                "Привет".encode("utf-8"),
                {"Content-Type": "text/html; charset=no-such-charset"},
            )
        elif self.path == "/redirect":
            self._send(302, b"", {"Location": "/page"})
        elif self.path == "/redirect-external":
            self._send(302, b"", {"Location": "http://evil.example/x"})
        elif self.path == "/loop":
            self._send(302, b"", {"Location": "/loop"})
        else:
            self._send(404, b"", {"Content-Type": "text/html"})


class HttpFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.requests = []
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        thread = Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.port = self.server.server_address[1]

    def fetch(self, path: str, *, max_bytes: int = 1024 * 1024, max_chars: int = 10_000):
        return http_fetch.fetch_text(
            f"http://example.com:{self.port}{path}",
            max_bytes=max_bytes,
            max_chars=max_chars,
            timeout=5,
        )

    def _allow_local(self):
        """Резолвер, отдающий локальный IP: pinning коннектится на него."""
        resolver = mock.Mock(return_value=["127.0.0.1"])
        patcher = mock.patch.object(http_fetch, "_public_ips", resolver)
        patcher.start()
        self.addCleanup(patcher.stop)
        return resolver

    # ---------- валидация адреса ----------

    def test_scheme_host_and_port_are_validated(self) -> None:
        for url in (
            "file:///etc/passwd",
            "ftp://example.com/x",
            "http://",
            "http://example.com:99999/x",
        ):
            with self.subTest(url=url):
                with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                    http_fetch.fetch_text(
                        url, max_bytes=1024, max_chars=1024, timeout=1
                    )
                self.assertEqual(ctx.exception.status_code, 422)

    def test_private_loopback_and_link_local_are_rejected(self) -> None:
        for url in (
            "http://127.0.0.1/x",
            "http://[::1]/x",
            "http://10.0.0.1/x",
            "http://192.168.1.1/x",
            "http://169.254.169.254/latest/meta-data",
        ):
            with self.subTest(url=url):
                with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                    http_fetch.fetch_text(
                        url, max_bytes=1024, max_chars=1024, timeout=1
                    )
                self.assertEqual(ctx.exception.status_code, 422)
        for url in ("http://127.0.0.1/x", "http://10.0.0.1/x"):
            with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                http_fetch.fetch_text(
                    url, max_bytes=1024, max_chars=1024, timeout=1
                )
            self.assertIn("private", ctx.exception.detail)

    # ---------- pinning ----------

    def test_nat64_and_ipv4_compatible_are_rejected(self) -> None:
        """NAT64/IPv4-compatible упаковка внутреннего IPv4 (гайд: security-gate)."""
        for literal in (
            "64:ff9b::7f00:1",     # NAT64 127.0.0.1
            "64:ff9b:1::a00:1",    # local-use NAT64 10.0.0.1
            "::7f00:1",            # IPv4-compatible 127.0.0.1
            "224.0.0.1",           # multicast IPv4
            "ff02::1",             # multicast IPv6
            "192.0.0.1",           # IETF protocol assignments
        ):
            with self.subTest(literal=literal):
                with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                    http_fetch._public_ips(literal, 80)
                self.assertEqual(ctx.exception.status_code, 422)
                self.assertIn("private", ctx.exception.detail)
        # Контроль: глобальный IPv6 не блокируется.
        self.assertEqual(
            http_fetch._public_ips("2606:4700:4700::1111", 443),
            ["2606:4700:4700::1111"],
        )

    def test_connect_timeout_tries_next_ip(self) -> None:
        sentinel = object()
        with mock.patch.object(
            httpcore.SyncBackend,
            "connect_tcp",
            side_effect=[httpcore.ConnectTimeout("connect timeout"), sentinel],
        ) as connect:
            backend = http_fetch._PinnedBackend(["203.0.113.1", "203.0.113.2"])
            result = backend.connect_tcp("example.com", 443)
        self.assertIs(result, sentinel)
        self.assertEqual(connect.call_args.args[:2], ("203.0.113.2", 443))

    def test_unknown_charset_falls_back_to_utf8(self) -> None:
        self._allow_local()
        text, _ = self.fetch("/badcharset")
        self.assertIn("Привет", text)

    def test_fastapi_supports_max_body_size(self) -> None:
        """F3 держится на нативном `FastAPI(max_body_size=...)` (pin в requirements)."""
        import inspect

        from fastapi import FastAPI

        self.assertIn(
            "max_body_size", inspect.signature(FastAPI.__init__).parameters
        )

    def test_connect_tcp_gets_pinned_ip(self) -> None:
        """TCP-коннект идёт на проверенный IP, а не на имя из URL."""
        sentinel = object()
        with mock.patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=sentinel
        ) as connect:
            backend = http_fetch._PinnedBackend(["203.0.113.7", "203.0.113.8"])
            result = backend.connect_tcp("example.com", 443)
        self.assertIs(result, sentinel)
        self.assertEqual(connect.call_args.args[:2], ("203.0.113.7", 443))

    def test_fetch_uses_resolved_ip_and_keeps_original_host(self) -> None:
        resolver = self._allow_local()
        text, title = self.fetch("/page")
        self.assertEqual(title, "Статья про бюджет")
        self.assertIn("Иван Петров", text)
        self.assertNotIn("var hidden", text)
        resolver.assert_called_with("example.com", self.port)
        # Сервер получил исходный Host — значит подключились на IP, а не на имя.
        self.assertEqual(
            self.server.requests, [("/page", f"example.com:{self.port}")]
        )

    def test_tls_uses_origin_host_as_sni(self) -> None:
        """SNI/Host — исходный host; pinning подменяет только TCP-адрес."""
        connected: list[tuple[str, int]] = []
        sni: list[str | None] = []

        class _FakeStream:
            def read(self, max_bytes, timeout=None):
                return b""  # обрыв: дальше HTTP-парсинг не нужен

            def write(self, buffer, timeout=None):
                pass

            def close(self):
                pass

            def get_extra_info(self, info):
                return None

            def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                sni.append(server_hostname)
                return self

        def connect_tcp(self, host, port, **kwargs):
            connected.append((host, port))
            return _FakeStream()

        with mock.patch.object(httpcore.SyncBackend, "connect_tcp", connect_tcp):
            transport = http_fetch.PinnedTransport(["203.0.113.7"])
            with self.assertRaises(httpx.HTTPError):
                with httpx.Client(transport=transport, timeout=1) as client:
                    client.get("https://example.com/secure")
        self.assertEqual(connected, [("203.0.113.7", 443)])
        self.assertEqual(sni, ["example.com"])

    def test_redirects_are_rechecked_per_hop(self) -> None:
        calls: list[tuple[str, int]] = []

        def resolve(host: str, port: int) -> list[str]:
            calls.append((host, port))
            if host == "evil.example":
                raise http_fetch.HttpFetchError(
                    422, "url points to a private address"
                )
            return ["127.0.0.1"]

        with mock.patch.object(http_fetch, "_public_ips", side_effect=resolve):
            text, title = self.fetch("/redirect")
            self.assertIn("Иван Петров", text)
            with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                self.fetch("/redirect-external")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(
            [host for host, _ in calls],
            ["example.com", "example.com", "example.com", "evil.example"],
        )

    def test_too_many_redirects(self) -> None:
        self._allow_local()
        with self.assertRaises(http_fetch.HttpFetchError) as ctx:
            self.fetch("/loop")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("too many redirects", ctx.exception.detail)

    # ---------- содержимое и лимиты ----------

    def test_content_type_allowlist(self) -> None:
        self._allow_local()
        with self.assertRaises(http_fetch.HttpFetchError) as ctx:
            self.fetch("/pdf")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("content type", ctx.exception.detail)

    def test_plain_text_page(self) -> None:
        self._allow_local()
        text, title = self.fetch("/plain")
        self.assertIn("hello plain", text)
        self.assertEqual(title, "")

    def test_max_bytes_limits_stream(self) -> None:
        self._allow_local()
        with self.assertRaises(http_fetch.HttpFetchError) as ctx:
            self.fetch("/big", max_bytes=1024)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("url content exceeds", ctx.exception.detail)

    def test_max_chars_truncates_text(self) -> None:
        self._allow_local()
        text, _ = self.fetch("/long", max_chars=40)
        self.assertLessEqual(len(text.strip()), 40)

    def test_http_error_status(self) -> None:
        self._allow_local()
        with self.assertRaises(http_fetch.HttpFetchError) as ctx:
            self.fetch("/missing")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("url returned 404", ctx.exception.detail)

    def test_unresolvable_host(self) -> None:
        with mock.patch.object(
            http_fetch.socket, "getaddrinfo", side_effect=OSError("no dns")
        ):
            with self.assertRaises(http_fetch.HttpFetchError) as ctx:
                http_fetch.fetch_text(
                    "http://no-such-host.invalid/x",
                    max_bytes=1024,
                    max_chars=1024,
                    timeout=1,
                )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("cannot be resolved", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
