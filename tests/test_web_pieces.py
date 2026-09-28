"""Bộ quân phải đủ 12 file, hợp lệ, và có ghi công."""

import unittest
from pathlib import Path

PIECES = Path(__file__).resolve().parent.parent / "chessai" / "web" / "static" / "pieces"
NAMES = [f"{c}{p}" for c in "wb" for p in "KQRBNP"]


class TestPieces(unittest.TestCase):
    def test_all_twelve_files_exist(self) -> None:
        for name in NAMES:
            with self.subTest(name=name):
                self.assertTrue((PIECES / f"{name}.svg").is_file(), f"thiếu {name}.svg")

    def test_files_are_svg(self) -> None:
        for name in NAMES:
            with self.subTest(name=name):
                text = (PIECES / f"{name}.svg").read_text(encoding="utf-8")
                self.assertIn("<svg", text[:400])

    def test_total_size_under_40kb(self) -> None:
        total = sum((PIECES / f"{n}.svg").stat().st_size for n in NAMES)
        self.assertLess(total, 40 * 1024, f"tong {total} byte")

    def test_credits_states_author_and_license(self) -> None:
        text = (PIECES / "CREDITS.md").read_text(encoding="utf-8")
        self.assertIn("Colin Burnett", text)
        self.assertIn("CC BY-SA 3.0", text)

    def test_no_unexpected_files(self) -> None:
        present = {p.stem for p in PIECES.glob("*")}
        self.assertEqual(present - set(NAMES), {"CREDITS"}, f"file la: {present}")
