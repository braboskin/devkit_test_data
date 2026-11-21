import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import chunking  # noqa: E402


def count_words(text: str) -> int:
    return len(text.split())


class ChunkingTests(unittest.TestCase):
    def test_chunks_are_within_bounds(self):
        text = "\n\n".join(
            f"Sentence {i} has a few words for chunk testing."
            for i in range(300)
        )
        chunks = chunking.chunk_text(text, count_words)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks[:-1]:
            self.assertGreaterEqual(chunk["token_count"], chunking.MIN_TOKENS)
            self.assertLessEqual(chunk["token_count"], chunking.MAX_TOKENS)
        for chunk in chunks:
            self.assertGreater(chunk["token_count"], 0)

    def test_overlap_between_neighbours(self):
        text = "\n\n".join(
            f"Sentence {i} has a few words for chunk testing."
            for i in range(300)
        )
        chunks = chunking.chunk_text(text, count_words)
        first = chunks[0]["text"].split()
        second = chunks[1]["text"].split()

        common = 0
        for size in range(1, min(len(first), len(second)) + 1):
            if first[-size:] == second[:size]:
                common = size
        self.assertGreaterEqual(common, 5)

    def test_short_text_single_chunk(self):
        chunks = chunking.chunk_text("Короткая заметка про сон.", count_words)
        self.assertEqual(len(chunks), 1)
        self.assertLess(chunks[0]["token_count"], chunking.MIN_TOKENS)


if __name__ == "__main__":
    unittest.main()
