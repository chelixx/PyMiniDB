"""Минимальное файловое хранилище: схема в .schema, записи в .csv."""

import csv
import math
from pathlib import Path
import re


def check_name(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Недопустимое имя: {name}")


def convert(value, kind):
    try:
        if kind == "INT":
            return int(value)
        if kind == "FLOAT":
            number = float(value)
            if not math.isfinite(number):
                raise ValueError
            return number
        if kind == "STRING":
            return str(value)
    except ValueError:
        raise ValueError(f"Значение {value!r} не подходит для {kind}") from None
    raise ValueError(f"Неизвестный тип: {kind}")


class Database:
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.mkdir(parents=True, exist_ok=True)

    def _file(self, table, suffix):
        check_name(table)
        return self.path / f"{table}.{suffix}"

    def tables(self):
        return sorted(file.stem for file in self.path.glob("*.schema"))

    def schema(self, table):
        path = self._file(table, "schema")
        if not path.exists():
            raise ValueError(f"Таблица {table} не существует")
        with path.open(encoding="utf-8", newline="") as file:
            return [tuple(row) for row in csv.reader(file)]

    def create(self, table, definitions):
        schema_path = self._file(table, "schema")
        data_path = self._file(table, "csv")
        if schema_path.exists() or data_path.exists():
            raise ValueError(f"Таблица {table} уже существует")
        columns = []
        for definition in definitions:
            parts = definition.split(":")
            if len(parts) not in (2, 3):
                raise ValueError("Формат поля: имя:ТИП или имя:ТИП:PK")
            name, kind = parts[:2]
            check_name(name)
            kind = kind.upper()
            if kind not in ("INT", "STRING", "FLOAT"):
                raise ValueError(f"Неизвестный тип: {kind}")
            primary = len(parts) == 3
            if primary and parts[2].upper() != "PK":
                raise ValueError("После типа допускается только :PK")
            if name in [column[0] for column in columns]:
                raise ValueError(f"Повтор поля: {name}")
            columns.append((name, kind, "PK" if primary else ""))
        if not columns or sum(column[2] == "PK" for column in columns) != 1:
            raise ValueError("Укажите ровно один PRIMARY KEY через :PK")
        # Создание файлов только после проверки всей схемы.
        with data_path.open("x", encoding="utf-8", newline=""):
            pass
        try:
            with schema_path.open("x", encoding="utf-8", newline="") as file:
                csv.writer(file).writerows(columns)
        except OSError:
            data_path.unlink()
            raise

    def select(self, table):
        columns = self.schema(table)
        rows = []
        with self._file(table, "csv").open(encoding="utf-8", newline="") as file:
            for values in csv.reader(file):
                if len(values) != len(columns):
                    raise ValueError(f"Повреждены данные таблицы {table}")
                rows.append({name: convert(value, kind)
                             for (name, kind, _), value in zip(columns, values)})
        return rows

    def insert(self, table, values):
        columns = self.schema(table)
        if len(values) != len(columns):
            raise ValueError(f"Ожидается значений: {len(columns)}, получено: {len(values)}")
        row = {name: convert(value, kind)
               for (name, kind, _), value in zip(columns, values)}
        key = next(name for name, _, marker in columns if marker == "PK")
        if any(existing[key] == row[key] for existing in self.select(table)):
            raise ValueError(f"PRIMARY KEY {key}={row[key]} уже существует")
        with self._file(table, "csv").open("a", encoding="utf-8", newline="") as file:
            csv.writer(file).writerow(row.values())
        return row
