** MiniDB **
## Базовая версия

Нужен Python 3.8 или новее. Внешних зависимостей нет.

Запуск из папки проекта:

```sh
python3 main.py
```

Пример сеанса (это собственные CLI-команды, SQL-синтаксис из заметок выше пока не реализован):

```text
open data/demo
create datasets id:INT:PK name:STRING task:STRING size:INT
create models id:INT:PK name:STRING version:STRING
create experiments id:INT:PK dataset_id:INT model_id:INT accuracy:FLOAT status:STRING
insert datasets 1 "Тестовый датасет" classification 1000
insert models 1 "Simple Model" v1
insert experiments 1 1 1 0.91 completed
tables
select datasets
select experiments
exit
```

Запустите программу снова, выполните `open data/demo` и `select datasets`:
схема и записи сохраняются после выхода. Относительный путь базы считается от
текущей рабочей папки. ID вводятся явно; повтор PRIMARY KEY запрещён.
Значения при вставке передаются в порядке объявления полей. Для строк с пробелами
нужны кавычки, для FLOAT используется точка. Имена таблиц и полей: латинские
буквы, цифры и `_`, первый символ — буква или `_`.

### Устройство

- `main.py` — цикл ввода, разбор команд через `shlex`, вывод таблиц.
- `database.py` — создание таблиц, проверка типов и PK, чтение/запись файлов.
- `<таблица>.schema` — текстовый CSV с именем, типом и отметкой PK для каждого поля.
- `<таблица>.csv` — значения записей без заголовка; кавычки, запятые и переносы
  строк обрабатывает стандартный модуль `csv`.

Это начальный этап, а не выполнение всего ТЗ. Пока нет UPDATE, DELETE,
фильтров, автоматических ID, проверки внешних ключей, JOIN и индексов.
Работа с одной базой из нескольких процессов одновременно не поддерживается.

Проверки: `python3 -m unittest discover -s tests -v`.
