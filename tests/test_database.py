import tempfile
import unittest
from unittest.mock import patch

from database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Database(self.directory.name)
        self.db.create("items", ["id:INT:PK", "name:STRING", "score:FLOAT"])

    def test_reopen_preserves_schema_types_and_special_characters(self):
        self.db.insert("items", ["1", 'Русский текст, "кавычки"\nстрока', "0.91"])
        reopened = Database(self.directory.name)
        self.assertEqual(reopened.tables(), ["items"])
        self.assertEqual(reopened.schema("items")[0], ("id", "INT", "PK"))
        self.assertEqual(reopened.select("items"), [
            {"id": 1, "name": 'Русский текст, "кавычки"\nстрока', "score": 0.91}])

    def test_invalid_insert_does_not_change_data(self):
        self.db.insert("items", ["1", "first", "1.0"])
        for values in (["01", "duplicate", "2"], ["bad", "name", "2"],
                       ["2", "name", "nan"], ["2", "name"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.db.insert("items", values)
        self.assertEqual(len(self.db.select("items")), 1)

    def test_invalid_schema_creates_no_files(self):
        for definitions in (["id:INT"], ["id:INT:PK", "id:STRING"],
                            ["id:INT:PK", "other:INT:PK"], ["id:BOOL:PK"]):
            with self.subTest(definitions=definitions), self.assertRaises(ValueError):
                self.db.create("invalid", definitions)
        self.assertEqual(self.db.tables(), ["items"])
        self.assertFalse((self.db.path / "invalid.csv").exists())

    def test_duplicate_table_does_not_erase_records(self):
        self.db.insert("items", ["1", "saved", "2"])
        with self.assertRaises(ValueError):
            self.db.create("items", ["id:INT:PK"])
        self.assertEqual(self.db.select("items")[0]["name"], "saved")

    def test_insert_many_persists_all_rows(self):
        self.db.insert("items", ["1", "existing", "1"])
        rows = self.db.insert_many("items", [
            ["2", 'Текст, "кавычки"\nстрока', "0.2"], ["3", "third", "0.3"]])
        reopened = Database(self.directory.name).select("items")
        self.assertEqual([row["id"] for row in reopened], [1, 2, 3])
        self.assertEqual(reopened[1:], rows)

    def test_invalid_batch_leaves_file_unchanged(self):
        self.db.insert("items", ["1", "existing", "1"])
        path = self.db.path / "items.csv"
        original = path.read_bytes()
        invalid_batches = [
            [["2", "valid", "2"], ["1", "existing duplicate", "3"]],
            [["2", "valid", "2"], ["02", "batch duplicate", "3"]],
            [["2", "valid", "2"], ["3", "invalid", "bad float"]],
            [["2", "valid", "2"], ["3", "missing field"]],
            [],
        ]
        for batch in invalid_batches:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                self.db.insert_many("items", batch)
            self.assertEqual(path.read_bytes(), original)

    def test_failed_replace_preserves_data_and_removes_temporary_file(self):
        self.db.insert("items", ["1", "existing", "1"])
        path = self.db.path / "items.csv"
        original = path.read_bytes()
        with patch("database.Path.replace", side_effect=OSError("Ошибка записи")):
            with self.assertRaises(OSError):
                self.db.insert_many("items", [["2", "new", "2"]])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.db.path.glob("*.tmp")), [])

    def test_table_name_cannot_escape_database_directory(self):
        with self.assertRaises(ValueError):
            self.db.create("../outside", ["id:INT:PK"])


if __name__ == "__main__":
    unittest.main()
