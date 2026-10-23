from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from database import Database
from seed import create_demo


PROJECT = Path(__file__).resolve().parents[1]


class DefenseTests(unittest.TestCase):
    def test_full_defense_scenario_two_cli_processes(self):
        result = subprocess.run([sys.executable, str(PROJECT / "demo.py")],
                                cwd=PROJECT, capture_output=True, text=True, check=True)
        self.assertIn("Проверка пройдена", result.stdout)
        self.assertEqual(result.stdout.count("Ошибка:"), 7)
        self.assertNotIn("Traceback", result.stderr)

    def test_shipped_sample_matches_generator(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = Database(create_demo(Path(temporary) / "database"))
            shipped = Database(PROJECT / "data" / "sample")
            self.assertEqual(shipped.tables(), generated.tables())
            for table in generated.tables():
                self.assertEqual(shipped.schema(table), generated.schema(table))
                self.assertEqual(shipped.select(table), generated.select(table))

    def test_cli_eof_then_reopen_and_continue_auto_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = subprocess.run([sys.executable, str(PROJECT / "main.py")],
                                   input=f'open "{temporary}"\ncreate items id:INT:PK name:STRING\n'
                                         'insert items "До EOF"\n',
                                   capture_output=True, text=True, check=True)
            self.assertIn("Выход", first.stdout)
            second = subprocess.run([sys.executable, str(PROJECT / "main.py")],
                                    input=f'open "{temporary}"\ninsert items "После EOF"\nexit\n',
                                    capture_output=True, text=True, check=True)
            self.assertIn("id=2", second.stdout)
            self.assertEqual([row["id"] for row in Database(temporary).select("items")], [1, 2])

    def test_seed_cli_refuses_existing_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = create_demo(Path(temporary) / "database")
            before = {p.name: p.read_bytes() for p in path.iterdir()}
            result = subprocess.run([sys.executable, str(PROJECT / "seed.py"), str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("уже существует", result.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in path.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
