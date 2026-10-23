from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from database import Database
from seed import create_demo


class AutoIDTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Database(self.directory.name)
        self.db.create("items", ["id:INT:PK", "name:STRING", "score:FLOAT"])

    def test_auto_manual_batch_and_reopen(self):
        self.assertEqual(self.db.insert("items", ["first", "0.1"])["id"], 1)
        self.db.insert("items", ["10", "manual", "0.2"])
        rows = self.db.insert_many("items", [["auto", "0.3"], ["20", "manual", "0.4"],
                                             ["last", "0.5"]])
        self.assertEqual([row["id"] for row in rows], [21, 20, 22])
        reopened = Database(self.directory.name)
        self.assertEqual(reopened.insert("items", ["reopened", "0.6"])["id"], 23)
        self.assertEqual(len(reopened.select("items")), 6)

    def test_auto_id_follows_current_maximum_after_update_delete(self):
        self.db.insert("items", ["first", "0.1"])
        self.db.update("items", {"id": "50"})
        self.assertEqual(self.db.insert("items", ["second", "0.2"])["id"], 51)
        self.db.delete("items", ("id", "=", "51"))
        self.assertEqual(self.db.insert("items", ["reused", "0.3"])["id"], 51)
        self.db.delete("items")
        self.assertEqual(self.db.insert("items", ["restart", "0.1"])["id"], 1)

    def test_invalid_batch_and_write_failure_do_not_consume_ids(self):
        original = (self.db.path / "items.csv").read_bytes()
        with self.assertRaises(ValueError):
            self.db.insert_many("items", [["valid", "0.1"], ["invalid", "bad"]])
        with patch("database.Path.replace", side_effect=OSError("Ошибка записи")):
            with self.assertRaises(OSError):
                self.db.insert("items", ["valid", "0.1"])
        self.assertEqual((self.db.path / "items.csv").read_bytes(), original)
        self.assertEqual(self.db.insert("items", ["first", "0.1"])["id"], 1)

    def test_id_in_middle_and_id_only(self):
        self.db.create("middle", ["name:STRING", "id:INT:PK", "score:FLOAT"])
        self.assertEqual(self.db.insert("middle", ["name", "0.5"]),
                         {"name": "name", "id": 1, "score": 0.5})
        self.db.create("ids", ["id:INT:PK"])
        self.assertEqual([row["id"] for row in self.db.insert_many("ids", [[], []])], [1, 2])

    def test_other_primary_keys_still_require_explicit_values(self):
        for table, definitions in (("codes", ["code:INT:PK", "name:STRING"]),
                                   ("strings", ["id:STRING:PK", "name:STRING"])):
            self.db.create(table, definitions)
            with self.assertRaises(ValueError):
                self.db.insert(table, ["missing"])
            self.db.insert(table, ["1", "explicit"])

    def test_cli_automatic_and_explicit_modes(self):
        project = Path(__file__).resolve().parents[1]
        commands = (
            f'open "{self.directory.name}"\n'
            'insert items "Первый элемент" 0.1\n'
            'insert_many items --auto-id second 0.2 third 0.3 fourth 0.4\n'
            'insert items 20 manual 0.5\n'
            'insert_many items 21 explicit 0.6 22 explicit 0.7\n'
            'insert_many items --auto-id\n'
            'create codes code:INT:PK name:STRING\n'
            'insert_many codes --auto-id invalid\n'
            'create ids id:INT:PK\n'
            'insert ids\n'
            'exit\n')
        result = subprocess.run([sys.executable, str(project / "main.py")], input=commands,
                                capture_output=True, text=True, check=True)
        self.assertIn('Запись добавлена (id=1)', result.stdout)
        self.assertIn('Добавлено записей: 3', result.stdout)
        self.assertEqual(result.stdout.count('Ошибка:'), 2)
        self.assertEqual([row['id'] for row in self.db.select('items')],
                         [1, 2, 3, 4, 20, 21, 22])
        self.assertEqual(self.db.select('ids'), [{'id': 1}])


class DemoTests(unittest.TestCase):
    def test_demo_counts_links_reproducibility_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = create_demo(Path(temporary) / 'first')
            second = create_demo(Path(temporary) / 'second')
            db = Database(first)
            self.assertEqual([len(db.select(table)) for table in
                              ('datasets', 'models', 'experiments')], [5, 5, 20])
            for table in db.tables():
                self.assertEqual(db.select(table), Database(second).select(table))
            for row in db.select('experiments'):
                self.assertIn(row['dataset_id'], {item['id'] for item in db.select('datasets')})
                self.assertIn(row['model_id'], {item['id'] for item in db.select('models')})
            original = {p.name: p.read_bytes() for p in first.iterdir()}
            with self.assertRaises(ValueError):
                create_demo(first)
            self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()}, original)
            # Авто-ID не отключает проверку внешних ключей.
            with self.assertRaisesRegex(ValueError, 'FK'):
                db.insert('experiments', ['999', '1', '0.8', 'running'])
            self.assertEqual(db.insert('experiments', ['1', '1', '0.8', 'running'])['id'], 21)


if __name__ == '__main__':
    unittest.main()
