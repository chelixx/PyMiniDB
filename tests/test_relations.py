from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from database import Database


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Database(self.directory.name)
        self.db.create("datasets", ["id:INT:PK", "name:STRING"])
        self.db.create("models", ["id:INT:PK", "name:STRING"])
        self.db.create("experiments", ["id:INT:PK", "dataset_id:INT",
                                       "model_id:INT", "accuracy:FLOAT"])
        for table in ("datasets", "models"):
            self.db.insert_many(table, [["1", "used"], ["2", "free"]])
        self.db.insert("experiments", ["1", "1", "1", "0.9"])

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.db.path.iterdir()}

    def assert_rejected_unchanged(self, operation, message):
        original = self.snapshot()
        with self.assertRaisesRegex(ValueError, message):
            operation()
        self.assertEqual(self.snapshot(), original)

    def test_insert_rejects_missing_dataset_and_model(self):
        for values in (["2", "999", "1", "0.8"], ["2", "1", "999", "0.8"]):
            with self.subTest(values=values):
                self.assert_rejected_unchanged(
                    lambda: self.db.insert("experiments", values), "Неверный FK")

    def test_invalid_batch_is_atomic(self):
        self.assert_rejected_unchanged(
            lambda: self.db.insert_many("experiments", [
                ["2", "2", "2", "0.8"], ["3", "999", "2", "0.7"]]),
            "Неверный FK")

    def test_update_experiment_checks_both_foreign_keys(self):
        for field in ("dataset_id", "model_id"):
            with self.subTest(field=field):
                self.assert_rejected_unchanged(
                    lambda: self.db.update("experiments", {field: "999"}), "Неверный FK")
                self.assertEqual(self.db.update("experiments", {field: "2"}), 1)
        self.assertEqual(Database(self.directory.name).select("experiments")[0],
                         {"id": 1, "dataset_id": 2, "model_id": 2, "accuracy": 0.9})

    def test_referenced_parent_cannot_be_deleted_or_renumbered(self):
        for table in ("datasets", "models"):
            with self.subTest(table=table):
                self.assert_rejected_unchanged(
                    lambda: self.db.delete(table, ("id", "=", "1")), "ссылается")
                self.assert_rejected_unchanged(
                    lambda: self.db.update(table, {"id": "10"}, ("id", "=", "1")),
                    "ссылается")
                self.assert_rejected_unchanged(lambda: self.db.delete(table), "ссылается")

    def test_parent_non_id_update_and_same_id_are_allowed(self):
        for table in ("datasets", "models"):
            self.assertEqual(self.db.update(table, {"name": "renamed"}), 2)
            self.assertEqual(self.db.update(table, {"id": "1"}, ("id", "=", "1")), 1)

    def test_unreferenced_parent_ids_can_change_and_be_deleted(self):
        for table in ("datasets", "models"):
            self.assertEqual(self.db.update(table, {"id": "10"}, ("id", "=", "2")), 1)
            self.assertEqual(self.db.delete(table, ("id", "=", "10")), 1)

    def test_reassignment_releases_old_parent(self):
        self.db.update("experiments", {"dataset_id": "2", "model_id": "2"})
        for table in ("datasets", "models"):
            self.assertEqual(self.db.delete(table, ("id", "=", "1")), 1)
            self.assert_rejected_unchanged(lambda: self.db.delete(table), "ссылается")
        self.assertEqual(self.db.delete("experiments"), 1)
        for table in ("datasets", "models"):
            self.assertEqual(self.db.delete(table), 1)

    def test_experiment_primary_key_can_change(self):
        self.assertEqual(self.db.update("experiments", {"id": "10"}), 1)
        self.assertEqual(self.db.select("experiments")[0]["id"], 10)

    def test_checks_work_after_reopen(self):
        self.db = Database(self.directory.name)
        self.assert_rejected_unchanged(lambda: self.db.delete("models"), "ссылается")
        self.assert_rejected_unchanged(
            lambda: self.db.insert("experiments", ["2", "999", "1", "0.8"]), "FK")

    def test_missing_parent_table_and_incompatible_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(directory)
            db.create("experiments", ["id:INT:PK", "dataset_id:INT", "model_id:INT"])
            with self.assertRaisesRegex(ValueError, "datasets не существует"):
                db.insert("experiments", ["1", "1", "1"])
            db.create("datasets", ["id:INT:PK"])
            db.insert("datasets", ["1"])
            with self.assertRaisesRegex(ValueError, "models не существует"):
                db.insert("experiments", ["1", "1", "1"])
            self.assertEqual(db.select("experiments"), [])
        for table, definitions in (
                ("datasets", ["id:STRING:PK"]),
                ("models", ["other:INT:PK"]),
                ("experiments", ["id:INT:PK", "dataset_id:STRING", "model_id:INT"]),
                ("experiments", ["id:INT:PK", "dataset_id:INT"])):
            with self.subTest(table=table), tempfile.TemporaryDirectory() as directory:
                db = Database(directory)
                with self.assertRaises(ValueError):
                    db.create(table, definitions)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cli_reports_fk_errors_and_preserves_data_after_restart(self):
        project = Path(__file__).resolve().parents[1]
        commands = (
            f'open "{self.directory.name}"\n'
            'insert experiments 2 999 1 0.8\n'
            'insert_many experiments 2 2 2 0.8 3 1 999 0.7\n'
            'update experiments set dataset_id 999 where id = 1\n'
            'update experiments set model_id 999 where id = 1\n'
            'delete datasets where id = 1\n'
            'delete models\n'
            'update models set id 10 where id = 1\n'
            'update datasets set id 10 where id = 1\n'
            'update datasets set name renamed where id = 1\n'
            'exit\n')
        result = subprocess.run([sys.executable, str(project / 'main.py')],
                                input=commands, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.count('Ошибка:'), 8)
        self.assertIn('Изменено записей: 1', result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        reopened = Database(self.directory.name)
        self.assertEqual(reopened.select('datasets')[0]['name'], 'renamed')
        self.assertEqual(len(reopened.select('experiments')), 1)
        self.assertEqual(reopened.select('models')[0]['id'], 1)


if __name__ == '__main__':
    unittest.main()
