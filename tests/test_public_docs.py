from pathlib import Path
import subprocess
import unittest


class PublicDocsTests(unittest.TestCase):
    def test_public_docs_and_scripts_use_portable_examples(self):
        root = Path(__file__).resolve().parents[1]
        public_files = _tracked_public_files(root)
        banned = [
            "D:\\",
            "D:/文档",
            "\\wrf_learning",
            "geocompy",
            "--input-kind",
            "--score-metrics",
            "--report-dir",
            "--time-offset-hours",
            "--local-day-boundary-hour",
        ]
        for path in public_files:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8-sig")
            for item in banned:
                with self.subTest(path=path.relative_to(root), item=item):
                    self.assertNotIn(item, text)


def _tracked_public_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "README.md", "docs", "scripts", "environment.yml"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [root / line.strip() for line in result.stdout.splitlines() if line.strip() and (root / line.strip()).exists()]


if __name__ == "__main__":
    unittest.main()
