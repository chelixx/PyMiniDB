from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from database import Database


class CLITests(unittest.TestCase):
    def test_select_filters_and_error_recovery(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            commands = (
                f'open "{directory}"\n'
                'create items id:INT:PK name:STRING score:FLOAT\n'
                'insert_many items 1 "Два слова" 0.1 10 other 0.9\n'
                'select items where id > 2\n'
                'select items WHERE name = "Два слова"\n'
                'select items where score <= 0.1\n'
                'select items where id = 99\n'
                'select items where missing = 1\n'
                'select items where id = bad\n'
                'select items where id == 1\n'
                'select items where id>=1\n'
                'select items\n'
                'exit\n')
            result = subprocess.run(
                [sys.executable, str(project / 'main.py')], input=commands,
                capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.count('Записей: 1'), 3)
            self.assertIn('Записей: 0', result.stdout)
            self.assertIn('Записей: 2', result.stdout)
            self.assertEqual(result.stdout.count('Ошибка:'), 4)
            self.assertIn('Неизвестное поле', result.stdout)
            self.assertIn('Неизвестный оператор', result.stdout)
            self.assertNotIn('Traceback', result.stderr)

    def test_update_delete_and_reopen(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            commands = (
                f'open "{directory}"\n'
                'create items id:INT:PK name:STRING score:FLOAT\n'
                'insert_many items 1 first 0.1 2 second 0.2 3 third 0.3\n'
                'update items SET name "Новое имя" WHERE id >= 2\n'
                'update items set score 0.9 where id = 3\n'
                'update items set id 2 where id = 3\n'
                'update items set score invalid where id = 3\n'
                'update items set name changed wher id = 3\n'
                'delete items where id = 1\n'
                'delete items where id = 99\n'
                'delete items wher id = 2\n'
                'update items\n'
                'exit\n')
            result = subprocess.run(
                [sys.executable, str(project / 'main.py')], input=commands,
                capture_output=True, text=True, check=True)
            self.assertIn('Изменено записей: 2', result.stdout)
            self.assertIn('Изменено записей: 1', result.stdout)
            self.assertIn('Удалено записей: 1', result.stdout)
            self.assertIn('Удалено записей: 0', result.stdout)
            self.assertEqual(result.stdout.count('Ошибка:'), 5)
            reopened = subprocess.run(
                [sys.executable, str(project / 'main.py')],
                input=(f'open "{directory}"\nselect items\n'
                       'update items set score 1\ndelete items\nselect items\nexit\n'),
                capture_output=True, text=True, check=True)
            self.assertIn('Новое имя', reopened.stdout)
            self.assertIn('0.9', reopened.stdout)
            self.assertIn('Записей: 2', reopened.stdout)
            self.assertIn('Изменено записей: 2', reopened.stdout)
            self.assertIn('Удалено записей: 2', reopened.stdout)
            self.assertIn('Записей: 0', reopened.stdout)
            self.assertNotIn('Ошибка:', reopened.stdout)

    def test_insert_many_and_errors_then_reopen(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            commands = (
                f'open "{directory}"\n'
                'create items id:INT:PK name:STRING score:FLOAT\n'
                'insert items 1 existing 1\n'
                'insert_many items 2 "Два слова" 0.2 3 "a;b" 0.3\n'
                'insert_many items 4 good 0.4 5 missing\n'
                'insert_many items 4 good 0.4 2 duplicate 0.5\n'
                'insert_many items 4 good 0.4 5 bad invalid\n'
                'exit\n')
            result = subprocess.run(
                [sys.executable, str(project / 'main.py')], input=commands,
                capture_output=True, text=True, check=True)
            self.assertIn('Добавлено записей: 2', result.stdout)
            self.assertEqual(result.stdout.count('Ошибка:'), 3)
            reopened = subprocess.run(
                [sys.executable, str(project / 'main.py')],
                input=f'open "{directory}"\nselect items\nexit\n',
                capture_output=True, text=True, check=True)
            self.assertIn('Записей: 3', reopened.stdout)
            self.assertIn('Два слова', reopened.stdout)
            self.assertIn('a;b', reopened.stdout)
            self.assertNotIn('good', [row['name'] for row in Database(directory).select('items')])


if __name__ == '__main__':
    unittest.main()
