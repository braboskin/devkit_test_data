import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_obsidian  # noqa: E402


class ImportObsidianTests(unittest.TestCase):
    def test_import_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            vault = tmp / "vault"
            out = tmp / "out"
            vault.mkdir()

            (vault / "note.md").write_text(
                "# Заголовок\n\n"
                "Ссылка [[Другая|алиас]] и ![[image.png]].\n\n"
                "#tag\n",
                encoding="utf-8",
            )
            (vault / "empty.md").write_text("", encoding="utf-8")
            (vault / "_system").mkdir()
            (vault / "_system" / "template.md").write_text(
                "template", encoding="utf-8"
            )

            with contextlib.redirect_stdout(io.StringIO()):
                code = import_obsidian.main(
                    ["--vault", str(vault), "--out", str(out)]
                )

            self.assertEqual(code, 0)
            self.assertTrue((out / "note.md").exists())
            text = (out / "note.md").read_text(encoding="utf-8")
            self.assertIn("source: obsidian", text)
            self.assertIn("алиас", text)
            self.assertIn("[вложение: image.png]", text)
            self.assertIn("tag", text)
            self.assertFalse((out / "empty.md").exists())
            self.assertFalse((out / "_system" / "template.md").exists())


if __name__ == "__main__":
    unittest.main()
