from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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
            self.assertNotIn('good', reopened.stdout)


if __name__ == '__main__':
    unittest.main()
