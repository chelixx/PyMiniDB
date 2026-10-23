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

    def test_select_numeric_comparisons(self):
        self.db.insert_many("items", [
            ["1", "first", "0.1"], ["2", "second", "0.5"],
            ["10", "third", "0.9"]])
        cases = {"=": [2], "!=": [1, 10], ">": [10], "<": [1],
                 ">=": [2, 10], "<=": [1, 2]}
        for operation, expected in cases.items():
            with self.subTest(operation=operation):
                rows = self.db.select("items", ("id", operation, "2"))
                self.assertEqual([row["id"] for row in rows], expected)
        self.assertEqual([row["id"] for row in self.db.select(
            "items", ("score", ">", "0.5"))], [10])

    def test_select_string_and_no_matches_does_not_change_file(self):
        self.db.insert_many("items", [["1", "Два слова", "0.1"],
                                      ["2", "два слова", "0.2"]])
        path = self.db.path / "items.csv"
        original = path.read_bytes()
        self.assertEqual([row["id"] for row in self.db.select(
            "items", ("name", "=", "Два слова"))], [1])
        self.assertEqual(self.db.select("items", ("id", ">", "100")), [])
        self.assertEqual(len(self.db.select("items")), 2)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_select_filter_rejected_even_on_empty_table(self):
        for condition in (("unknown", "=", "1"), ("id", "==", "1"),
                          ("id", "=", "bad"), ("score", ">", "nan"),
                          ("id", "=")):
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                self.db.select("items", condition)

    def test_update_and_delete_persist_after_reopen(self):
        self.db.insert_many("items", [["1", "first", "0.1"],
                                      ["2", "second", "0.2"], ["3", "third", "0.3"]])
        self.assertEqual(self.db.update(
            "items", {"name": 'Новое, "имя"\nстрока', "score": "0.9"},
            ("id", ">=", "2")), 2)
        self.assertEqual(self.db.delete("items", ("score", "<", "0.5")), 1)
        rows = Database(self.directory.name).select("items")
        self.assertEqual([row["id"] for row in rows], [2, 3])
        self.assertTrue(all(row["score"] == 0.9 for row in rows))
        self.assertEqual(rows[0]["name"], 'Новое, "имя"\nстрока')

    def test_update_primary_key_and_reject_duplicates_atomically(self):
        self.db.insert_many("items", [["1", "first", "0.1"], ["2", "second", "0.2"]])
        self.assertEqual(self.db.update("items", {"id": "10"}, ("id", "=", "1")), 1)
        path = self.db.path / "items.csv"
        original = path.read_bytes()
        for changes, where in (({"id": "02"}, ("id", "=", "10")),
                               ({"id": "99"}, None)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.db.update("items", changes, where)
            self.assertEqual(path.read_bytes(), original)

    def test_update_delete_all_and_no_matches(self):
        self.db.insert_many("items", [["1", "first", "0.1"], ["2", "second", "0.2"]])
        self.assertEqual(self.db.update("items", {"score": "0.8"}), 2)
        with patch.object(self.db, "_write_rows") as write:
            self.assertEqual(self.db.update("items", {"score": "0.1"},
                                            ("id", "=", "99")), 0)
            self.assertEqual(self.db.delete("items", ("id", "=", "99")), 0)
            write.assert_not_called()
        self.assertEqual(self.db.delete("items"), 2)
        self.assertEqual(Database(self.directory.name).select("items"), [])
        self.assertIn("items", self.db.tables())
        self.db.insert("items", ["1", "reused", "1"])

    def test_invalid_mutations_do_not_change_data_even_without_matches(self):
        for populated in (False, True):
            if populated:
                self.db.insert("items", ["1", "saved", "0.1"])
            original = (self.db.path / "items.csv").read_bytes()
            for changes in ({"missing": "1"}, {"score": "nan"}, {"id": "bad"}, {}):
                with self.subTest(changes=changes, populated=populated):
                    with self.assertRaises(ValueError):
                        self.db.update("items", changes, ("id", "=", "99"))
            for where in (("missing", "=", "1"), ("id", "==", "1"),
                          ("id", "=", "bad")):
                with self.assertRaises(ValueError):
                    self.db.update("items", {"name": "new"}, where)
                with self.assertRaises(ValueError):
                    self.db.delete("items", where)
            self.assertEqual((self.db.path / "items.csv").read_bytes(), original)

    def test_mutation_replace_failure_preserves_original(self):
        self.db.insert("items", ["1", "saved", "0.1"])
        path = self.db.path / "items.csv"
        original = path.read_bytes()
        with patch("database.Path.replace", side_effect=OSError("Ошибка записи")):
            with self.assertRaises(OSError):
                self.db.update("items", {"name": "new"})
            with self.assertRaises(OSError):
                self.db.delete("items")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.db.path.glob("*.tmp")), [])

    def test_table_name_cannot_escape_database_directory(self):
        with self.assertRaises(ValueError):
            self.db.create("../outside", ["id:INT:PK"])


if __name__ == "__main__":
    unittest.main()
