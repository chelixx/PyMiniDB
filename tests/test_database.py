import tempfile
import unittest

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

    def test_table_name_cannot_escape_database_directory(self):
        with self.assertRaises(ValueError):
            self.db.create("../outside", ["id:INT:PK"])


if __name__ == "__main__":
    unittest.main()
