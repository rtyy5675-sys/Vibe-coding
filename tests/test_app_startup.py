import tempfile
import unittest
from pathlib import Path

from mvp.app import create_app


class AppStartupTests(unittest.TestCase):
    def test_factory_creates_runtime_directories_and_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            app = create_app({"TESTING": True, "RUNTIME_ROOT": root})

            self.assertTrue(app.testing)
            self.assertTrue((root / "data" / "eval_mvp.sqlite").is_file())
            for relative_path in ("uploads", "runs", "reports/generated"):
                self.assertTrue((root / relative_path).is_dir())


if __name__ == "__main__":
    unittest.main()
