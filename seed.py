"""Создать отдельную тестовую базу: python3 seed.py [папка]."""

import argparse
from pathlib import Path
import tempfile

from database import Database


def create_demo(path):
    path = Path(path).expanduser().absolute()
    if path.exists():
        raise ValueError(f"Папка уже существует, выберите новую: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Готовим всю базу отдельно, чтобы ошибка не оставила частичные данные.
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".minidb_seed_") as temporary:
        staging = Path(temporary) / "database"
        db = Database(staging)
        db.create("datasets", ["id:INT:PK", "name:STRING", "task:STRING", "size:INT"])
        db.create("models", ["id:INT:PK", "name:STRING", "version:STRING"])
        db.create("experiments", ["id:INT:PK", "dataset_id:INT", "model_id:INT",
                                   "accuracy:FLOAT", "status:STRING"])
        datasets = db.insert_many("datasets", [
            ["Изображения", "classification", "1000"],
            ["Отзывы", "classification", "2500"],
            ["Цены квартир", "regression", "800"],
            ["Новости", "classification", "5000"],
            ["Показания датчиков", "regression", "1200"],
        ])
        models = db.insert_many("models", [
            ["Linear Model", "1.0"], ["Decision Tree", "1.0"],
            ["Random Forest", "2.0"], ["Neural Network", "1.1"],
            ["Gradient Boosting", "2.1"],
        ])
        db.insert_many("experiments", [
            [str(datasets[index % 5]["id"]), str(models[index // 4]["id"]),
             f"{0.70 + index * 0.01:.2f}", "running" if index % 4 == 0 else "completed"]
            for index in range(20)
        ])
        staging.rename(path)
    return path


def main():
    parser = argparse.ArgumentParser(description="Создать тестовую базу MiniDB (5/5/20 записей)")
    parser.add_argument("path", nargs="?", default="data/sample", help="Новая папка для базы")
    args = parser.parse_args()
    try:
        path = create_demo(args.path)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Ошибка: {error}\n")
    print(f"Тестовая база создана: {path}")
    print("datasets: 5; models: 5; experiments: 20")


if __name__ == "__main__":
    main()
