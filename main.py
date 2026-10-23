"""Интерактивный CLI MiniDB без сторонних зависимостей."""

import shlex

from database import Database


HELP = """Команды:
  open ПАПКА                         Создать или открыть базу
  create ТАБЛИЦА ПОЛЕ:ТИП:PK ...      Создать таблицу с одним PRIMARY KEY
  tables                             Список таблиц
  insert ТАБЛИЦА ЗНАЧЕНИЕ ...         Добавить запись в порядке полей
  insert_many ТАБЛИЦА [--auto-id] ЗНАЧЕНИЯ ...  Добавить несколько записей
  select ТАБЛИЦА [where ПОЛЕ ОП ЗНАЧЕНИЕ]  Показать записи с фильтром
  update ТАБЛИЦА set ПОЛЕ ЗНАЧЕНИЕ [where ПОЛЕ ОП ЗНАЧЕНИЕ]
  delete ТАБЛИЦА [where ПОЛЕ ОП ЗНАЧЕНИЕ]
  help                               Справка
  exit                               Выход
Типы: INT, STRING, FLOAT. Строки с пробелами заключайте в кавычки.
Авто-ID для id:INT:PK: в insert опустите ID; в insert_many укажите --auto-id.
ID = максимум текущих и ручных ID пакета + 1 (начиная с 1).
После удаления максимального ID его номер может использоваться снова.
Фильтр: =, !=, >, <, >=, <=. Ставьте пробелы вокруг оператора.
Пример: select datasets where size >= 1000
Пример: create datasets id:INT:PK name:STRING task:STRING size:INT
"""


def parse_where(tokens):
    if not tokens:
        return None
    if len(tokens) == 4 and tokens[0].lower() == "where":
        return tuple(tokens[1:])
    raise ValueError("Условие: where ПОЛЕ ОП ЗНАЧЕНИЕ. Ставьте пробелы вокруг оператора")


def show_rows(columns, rows):
    lines = [columns] + [[str(row[name]) for name in columns] for row in rows]
    widths = [max(len(line[index]) for line in lines) for index in range(len(columns))]
    for index, line in enumerate(lines):
        print(" | ".join(value.ljust(width) for value, width in zip(line, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))
    print(f"Записей: {len(rows)}")


def main():
    database = None
    print("MiniDB. Введите help для справки.")
    while True:
        try:
            tokens = shlex.split(input("minidb> "))
            if not tokens:
                continue
            command, *args = tokens
            command = command.lower()
            if command == "exit" and not args:
                break
            if command == "help" and not args:
                print(HELP)
                continue
            if command == "open":
                if len(args) != 1:
                    raise ValueError("Использование: open ПАПКА")
                database = Database(args[0])
                print(f"Открыта база: {database.path.resolve()}")
                continue
            if command not in ("create", "tables", "insert", "insert_many", "select", "update", "delete"):
                raise ValueError("Неизвестная команда или лишние аргументы. Введите help")
            if database is None:
                raise ValueError("Сначала откройте базу: open ПАПКА")
            if command == "create" and len(args) >= 2:
                database.create(args[0], args[1:])
                print("Таблица создана")
            elif command == "tables" and not args:
                print("\n".join(database.tables()) or "Таблиц пока нет")
            elif command == "insert" and args:
                added = database.insert(args[0], args[1:])
                key = next(name for name, _, marker in database.schema(args[0])
                           if marker == "PK")
                print(f"Запись добавлена ({key}={added[key]})")
            elif command == "insert_many" and len(args) >= 2:
                table, *values = args
                columns = database.schema(table)
                width = len(columns)
                if values and values[0] == "--auto-id":
                    if ("id", "INT", "PK") not in columns:
                        raise ValueError("Авто-ID требует поле id:INT:PK")
                    values = values[1:]
                    width -= 1
                    if width == 0:
                        raise ValueError("Для таблицы только с ID используйте insert ТАБЛИЦА")
                if not values or len(values) % width:
                    raise ValueError(
                        f"Для каждой записи нужно {width} значений; "
                        f"получено всего: {len(values)}")
                records = [values[start:start + width]
                           for start in range(0, len(values), width)]
                added = database.insert_many(table, records)
                print(f"Добавлено записей: {len(added)}")
            elif command == "select" and args:
                where = parse_where(args[1:])
                columns = [column[0] for column in database.schema(args[0])]
                show_rows(columns, database.select(args[0], where=where))
            elif command == "update":
                if len(args) < 4 or args[1].lower() != "set":
                    raise ValueError(
                        "Использование: update ТАБЛИЦА set ПОЛЕ ЗНАЧЕНИЕ "
                        "[where ПОЛЕ ОП ЗНАЧЕНИЕ]")
                where = parse_where(args[4:])
                count = database.update(args[0], {args[2]: args[3]}, where=where)
                print(f"Изменено записей: {count}")
            elif command == "delete" and args:
                where = parse_where(args[1:])
                count = database.delete(args[0], where=where)
                print(f"Удалено записей: {count}")
            else:
                raise ValueError("Неверные аргументы. Введите help")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход")
            break
        except (ValueError, OSError, UnicodeError) as error:
            print(f"Ошибка: {error}")


if __name__ == "__main__":
    main()
