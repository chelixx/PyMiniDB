"""Воспроизводимая демонстрация защиты в новой временной базе."""

from pathlib import Path
import subprocess
import sys
import tempfile

from database import Database
from seed import create_demo


PROJECT = Path(__file__).resolve().parent


def run_demo():
    with tempfile.TemporaryDirectory(prefix="minidb_defense_") as temporary:
        path = create_demo(Path(temporary) / "database")
        initial = Database(path)
        if [len(initial.select(table)) for table in ("datasets", "models", "experiments")] != [5, 5, 20]:
            raise RuntimeError("Неверные начальные количества записей")
        for session in (1, 2):
            commands = (PROJECT / "docs" / f"demo_session{session}.txt").read_text(encoding="utf-8")
            commands = commands.replace("open data/defense", f'open "{path}"', 1)
            print(f"=== Сеанс {session}: отдельный процесс CLI ===", flush=True)
            print("Команды:\n" + commands, flush=True)
            result = subprocess.run(
                [sys.executable, str(PROJECT / "main.py")], input=commands,
                capture_output=True, text=True, encoding="utf-8", check=True)
            print(result.stdout.replace(str(path), "<временная база>"), flush=True)
            expected_errors = 7 if session == 1 else 0
            if result.stderr or result.stdout.count("Ошибка:") != expected_errors:
                raise RuntimeError(f"Неожиданный результат сеанса {session}: {result.stderr}")
        db = Database(path)
        experiments = db.select("experiments")
        if len(experiments) != 20 or any(row["id"] == 20 for row in experiments):
            raise RuntimeError("DELETE не сохранился")
        row = db.select("experiments", ("id", "=", "21"))
        if row != [{"id": 21, "dataset_id": 6, "model_id": 6,
                    "accuracy": 0.95, "status": "completed"}]:
            raise RuntimeError("INSERT/UPDATE или откат ошибочной операции не сохранились")
        if db.select("datasets", ("id", "=", "6"))[0]["name"] != "Обновлённый датасет":
            raise RuntimeError("Имя датасета не сохранилось")
        if len(db.select("models")) != 8 or len(db.select("notes")) != 1:
            raise RuntimeError("Массовая вставка или создание таблицы не сохранились")
        print("Проверка пройдена: CRUD, 7 ожидаемых ошибок PK/FK, два запуска и сохранность данных.")


if __name__ == "__main__":
    run_demo()
