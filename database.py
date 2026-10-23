"""Минимальное файловое хранилище: схема в .schema, записи в .csv."""

import csv
import math
import operator
from pathlib import Path
import re
import tempfile


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


# Связи из ТЗ фиксированы: отдельный синтаксис объявления FK не нужен.
FOREIGN_KEYS = {"dataset_id": "datasets", "model_id": "models"}


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
        self._check_relation_schema(table, columns)
        # Создание файлов только после проверки всей схемы.
        with data_path.open("x", encoding="utf-8", newline=""):
            pass
        try:
            with schema_path.open("x", encoding="utf-8", newline="") as file:
                csv.writer(file).writerows(columns)
        except OSError:
            data_path.unlink()
            raise

    def _predicate(self, columns, where):
        if where is None:
            return lambda row: True
        if len(where) != 3:
            raise ValueError("Условие должно содержать поле, оператор и значение")
        field, operation, value = where
        types = {name: kind for name, kind, _ in columns}
        if field not in types:
            raise ValueError(f"Неизвестное поле: {field}")
        comparisons = {"=": operator.eq, "!=": operator.ne,
                       ">": operator.gt, "<": operator.lt,
                       ">=": operator.ge, "<=": operator.le}
        if operation not in comparisons:
            raise ValueError(f"Неизвестный оператор: {operation}")
        comparison = comparisons[operation]
        expected = convert(value, types[field])
        return lambda row: comparison(row[field], expected)

    def select(self, table, where=None):
        """Вернуть записи; where — тройка (поле, оператор, значение)."""
        columns = self.schema(table)
        matches = self._predicate(columns, where)
        rows = []
        with self._file(table, "csv").open(encoding="utf-8", newline="") as file:
            for values in csv.reader(file):
                if len(values) != len(columns):
                    raise ValueError(f"Повреждены данные таблицы {table}")
                row = {name: convert(value, kind)
                       for (name, kind, _), value in zip(columns, values)}
                if matches(row):
                    rows.append(row)
        return rows

    def insert(self, table, values):
        return self.insert_many(table, [values])[0]

    def insert_many(self, table, records):
        """Проверить весь пакет и сохранить его одной заменой файла."""
        columns = self.schema(table)
        existing = self.select(table)
        key = next(name for name, _, marker in columns if marker == "PK")
        auto_id = ("id", "INT", "PK") in columns
        rows = []
        for index, values in enumerate(records, start=1):
            try:
                if len(values) == len(columns):
                    fields = columns
                elif auto_id and len(values) == len(columns) - 1:
                    fields = [column for column in columns if column[0] != "id"]
                else:
                    raise ValueError(
                        f"Ожидается значений: {len(columns)}"
                        + (f" или {len(columns) - 1} без ID" if auto_id else "")
                        + f", получено: {len(values)}")
                row = {name: convert(value, kind)
                       for (name, kind, _), value in zip(fields, values)}
                rows.append(row)
            except ValueError as error:
                raise ValueError(f"Запись {index}: {error}") from None
        if not rows:
            raise ValueError("Не переданы записи для добавления")

        keys = {row[key] for row in existing}
        if auto_id:
            # Ручные ID всего пакета учитываются до назначения автоматических.
            reserved = keys | {row[key] for row in rows if key in row}
            next_id = max(reserved | {0}) + 1
        for index, row in enumerate(rows, start=1):
            if auto_id and key not in row:
                row[key] = next_id
                next_id += 1
            if row[key] in keys:
                raise ValueError(
                    f"Запись {index}: PRIMARY KEY {key}={row[key]} уже существует")
            keys.add(row[key])

        self._write_rows(table, columns, existing + rows)
        return rows

    def update(self, table, changes, where=None):
        """Изменить поля подходящих записей; вернуть их количество."""
        columns = self.schema(table)
        matches = self._predicate(columns, where)
        types = {name: kind for name, kind, _ in columns}
        if not changes:
            raise ValueError("Не указаны поля для изменения")
        converted = {}
        for name, value in changes.items():
            if name not in types:
                raise ValueError(f"Неизвестное поле: {name}")
            converted[name] = convert(value, types[name])
        rows = self.select(table)
        count = 0
        for row in rows:
            if matches(row):
                row.update(converted)
                count += 1
        key = next(name for name, _, marker in columns if marker == "PK")
        keys = set()
        for row in rows:
            if row[key] in keys:
                raise ValueError(f"PRIMARY KEY {key}={row[key]} уже существует")
            keys.add(row[key])
        if count:
            self._write_rows(table, columns, rows)
        return count

    def delete(self, table, where=None):
        """Удалить подходящие записи; вернуть их количество."""
        columns = self.schema(table)
        matches = self._predicate(columns, where)
        rows = self.select(table)
        remaining = [row for row in rows if not matches(row)]
        count = len(rows) - len(remaining)
        if count:
            self._write_rows(table, columns, remaining)
        return count

    def _check_relation_schema(self, table, columns):
        if table not in ("datasets", "models", "experiments"):
            return
        fields = {name: (kind, marker) for name, kind, marker in columns}
        if fields.get("id") != ("INT", "PK"):
            raise ValueError(f"Таблица {table}: требуется поле id:INT:PK")
        if table == "experiments":
            for field in FOREIGN_KEYS:
                if field not in fields or fields[field][0] != "INT":
                    raise ValueError(f"Таблица experiments: требуется поле {field}:INT")

    def _check_links(self, table, rows):
        """Проверить связи для итогового состояния изменяемой таблицы."""
        if table not in ("datasets", "models", "experiments"):
            return
        self._check_relation_schema(table, self.schema(table))
        if table == "experiments":
            if not rows:
                return
            for field, parent in FOREIGN_KEYS.items():
                self._check_relation_schema(parent, self.schema(parent))
                parent_ids = {row["id"] for row in self.select(parent)}
                for row in rows:
                    if row[field] not in parent_ids:
                        raise ValueError(
                            f"Неверный FK: experiments.{field}={row[field]} — "
                            f"нет записи в {parent}.id (experiment id={row['id']})")
        elif self._file("experiments", "schema").exists():
            self._check_relation_schema("experiments", self.schema("experiments"))
            field = next(field for field, parent in FOREIGN_KEYS.items() if parent == table)
            parent_ids = {row["id"] for row in rows}
            for experiment in self.select("experiments"):
                if experiment[field] not in parent_ids:
                    raise ValueError(
                        f"Нельзя удалить или изменить ID в {table}: "
                        f"experiment id={experiment['id']} ссылается на "
                        f"{table}.id={experiment[field]}")

    def _write_rows(self, table, columns, rows):
        self._check_links(table, rows)
        # Временный файл в папке базы: ошибка записи не изменит исходный файл.
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", dir=self.path,
                    prefix=f".{table}_", suffix=".tmp", delete=False) as file:
                temporary_path = Path(file.name)
                writer = csv.writer(file)
                for row in rows:
                    writer.writerow([row[name] for name, _, _ in columns])
            temporary_path.replace(self._file(table, "csv"))
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
