"""FR-13: smoke PWA-сборки viewer. Без `viewer/dist` тесты пропускаются."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.config import ROOT
from app.backend.db import Base
from app.backend.main import create_app

DIST = ROOT / "viewer" / "dist"


@unittest.skipUnless(
    (DIST / "index.html").is_file(),
    "viewer/dist не собран — пропускаем smoke PWA (соберите `npm run build` в viewer/)",
)
class WebBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{(Path(self.tmp.name) / 'web.db').as_posix()}"
        self.app = create_app(self.url)
        Base.metadata.create_all(self.app.state.engine)

    def tearDown(self) -> None:
        self.app.state.engine.dispose()
        self.tmp.cleanup()

    def test_root_serves_html_with_manifest_link(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("manifest.webmanifest", response.text)
        self.assertIn('id="root"', response.text)

    def test_manifest_is_installable(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        manifest = json.loads(response.text)
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue(manifest["name"])
        self.assertTrue(manifest["short_name"])
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)

    def test_icons_are_served(self) -> None:
        with TestClient(self.app) as client:
            for size in (192, 512):
                response = client.get(f"/icons/icon-{size}.png")
                self.assertEqual(response.status_code, 200, size)
                self.assertIn("image/png", response.headers["content-type"])

    def test_service_worker_served_and_keeps_api_out_of_cache(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("atlas-shell-v1", response.text)
        self.assertIn("/api/", response.text)
        self.assertIn("/offline.html", response.text)

    def test_navigation_falls_back_to_offline_page(self) -> None:
        script = (DIST / "sw.js").read_text(encoding="utf-8")
        shell = re.search(r"const SHELL = \[(.*?)\];", script, re.S)
        self.assertIsNotNone(shell, "в sw.js нет precache-списка SHELL")
        self.assertIn("'/offline.html'", shell.group(1), "offline.html должен быть в precache")

        offline_at = script.find("caches.match('/offline.html')")
        index_at = script.find("caches.match('/index.html')")
        self.assertGreaterEqual(offline_at, 0, "navigation-fallback не использует offline.html")
        self.assertGreaterEqual(index_at, 0, "нет запасного кэша index.html")
        self.assertLess(
            offline_at,
            index_at,
            "при офлайне сначала должна отдаваться offline.html, а не index.html",
        )

    def test_offline_page_is_self_contained(self) -> None:
        html = (DIST / "offline.html").read_text(encoding="utf-8")
        self.assertIn("Нет сети", html)
        self.assertIn('href="/"', html)
        self.assertNotIn("/api/", html, "офлайн-страница не должна обращаться к API")
        self.assertNotIn("fetch(", html, "офлайн-страница должна работать без JS-запросов")

    def test_app_distinguishes_offline_from_401(self) -> None:
        source = (ROOT / "viewer" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("status === 401", source, "сетевая ошибка не должна вести на форму входа")
        self.assertIn("setOffline(true)", source)
        self.assertIn("<Offline", source)

    def test_m2_screens_are_wired_into_build(self) -> None:
        source = (ROOT / "viewer" / "src" / "App.tsx").read_text(encoding="utf-8")
        for label in ("Документы", "Поиск", "Задания", "Настройки"):
            self.assertIn(label, source, f"нет вкладки «{label}» в App.tsx")
        bundle = "".join(
            path.read_text(encoding="utf-8") for path in (DIST / "assets").glob("*.js")
        )
        for endpoint in (
            "/api/documents",
            "/api/search",
            "/api/jobs",
            "/api/settings/yadisk",
            "/api/settings/worker-token",
        ):
            self.assertIn(endpoint, bundle, f"в сборке нет обращения к {endpoint}")

    def test_document_upload_sends_multipart(self) -> None:
        source = (ROOT / "viewer" / "src" / "api.ts").read_text(encoding="utf-8")
        self.assertIn(
            "instanceof FormData",
            source,
            "FormData нельзя отправлять с JSON Content-Type — сломается multipart",
        )


if __name__ == "__main__":
    unittest.main()
