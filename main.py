"""Интерактивный CLI MiniDB без сторонних зависимостей."""

import shlex

from database import Database


HELP = """Команды:
  open ПАПКА                         Создать или открыть базу
  create ТАБЛИЦА ПОЛЕ:ТИП:PK ...      Создать таблицу с одним PRIMARY KEY
  tables                             Список таблиц
  insert ТАБЛИЦА ЗНАЧЕНИЕ ...         Добавить запись в порядке полей
  insert_many ТАБЛИЦА ЗНАЧЕНИЯ ...    Добавить несколько записей подряд
  select ТАБЛИЦА                     Показать все записи
  help                               Справка
  exit                               Выход
Типы: INT, STRING, FLOAT. Строки с пробелами заключайте в кавычки.
Пример: create datasets id:INT:PK name:STRING task:STRING size:INT
"""


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
            if command not in ("create", "tables", "insert", "insert_many", "select"):
                raise ValueError("Неизвестная команда или лишние аргументы. Введите help")
            if database is None:
                raise ValueError("Сначала откройте базу: open ПАПКА")
            if command == "create" and len(args) >= 2:
                database.create(args[0], args[1:])
                print("Таблица создана")
            elif command == "tables" and not args:
                print("\n".join(database.tables()) or "Таблиц пока нет")
            elif command == "insert" and len(args) >= 2:
                database.insert(args[0], args[1:])
                print("Запись добавлена")
            elif command == "insert_many" and len(args) >= 2:
                table, *values = args
                width = len(database.schema(table))
                if len(values) % width:
                    raise ValueError(
                        f"Для каждой записи нужно {width} значений; "
                        f"получено всего: {len(values)}")
                records = [values[start:start + width]
                           for start in range(0, len(values), width)]
                added = database.insert_many(table, records)
                print(f"Добавлено записей: {len(added)}")
            elif command == "select" and len(args) == 1:
                columns = [column[0] for column in database.schema(args[0])]
                show_rows(columns, database.select(args[0]))
            else:
                raise ValueError("Неверные аргументы. Введите help")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход")
            break
        except (ValueError, OSError, UnicodeError) as error:
            print(f"Ошибка: {error}")


if __name__ == "__main__":
    main()
