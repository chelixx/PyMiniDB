"""Воспроизводимая демонстрация защиты в новой базе в папке проекта."""

from pathlib import Path
import subprocess
import sys
import argparse

from database import Database
from seed import create_demo


PROJECT = Path(__file__).resolve().parent


def create_test_database(path=None):
    if path is not None:
        return create_demo(path)
    path = PROJECT / "demo"
    number = 2
    while path.exists():
        path = PROJECT / f"demo_{number}"
        number += 1
    return create_demo(path)


def run_demo(path=None):
    path = create_test_database(path)
    print(f"База демонстрации: {path}", flush=True)
    initial = Database(path)
    if [len(initial.select(table)) for table in ("datasets", "models", "experiments")] != [5, 5, 20]:
        raise RuntimeError("Неверные начальные количества записей")
    for session in (1, 2):
        commands = (PROJECT / "docs" / f"demo_session{session}.txt").read_text(encoding="utf-8")
        lines = commands.splitlines()
        if not lines or not lines[0].startswith("open "):
            raise RuntimeError("Первая команда сеанса должна открывать базу")
        lines[0] = f'open "{path}"'
        commands = "\n".join(lines) + "\n"
        print(f"=== Сеанс {session}: отдельный процесс CLI ===", flush=True)
        print("Команды:\n" + commands, flush=True)
        result = subprocess.run(
            [sys.executable, str(PROJECT / "main.py")], input=commands,
            capture_output=True, text=True, encoding="utf-8", check=True)
        print(result.stdout, flush=True)
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
    print(f'База сохранена. Для открытия в CLI: open "{path}"')
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создать тестовую базу и показать работу MiniDB")
    parser.add_argument("path", nargs="?", help="Новая папка базы (по умолчанию demo, demo_2 и т.д.)")
    args = parser.parse_args()
    try:
        run_demo(args.path)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Ошибка демонстрации: {error}\n")
