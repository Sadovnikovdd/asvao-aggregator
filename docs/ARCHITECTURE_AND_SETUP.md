# Документация: ASVAO / агрегатор Excel-прайсов

Документ фиксирует всё, что было сделано в сессии: настройку LSP для проекта, факт-разбор Excel-файлов, архитектурное исследование on-prem ingest разношёрстных прайс-листов, выбранные политики, контракты, UI-настройки, observability и тестовую стратегию.

## Работающее локальное приложение

### Запуск

```bash
uv sync --group dev
uv run python -m aggregator
```

Используется uv-управляемый Python 3.12.14 из `.venv`; системный Python 3.9 не поддерживается — код использует синтаксис 3.10+.

Откройте `http://127.0.0.1:8000`. По умолчанию данные хранятся в `~/.aggregator`.
Чтобы использовать каталог данных и порт текущей демонстрации:

```bash
AGGREGATOR_PORT=8765 AGGREGATOR_DATA_DIR="$PWD/.aggregator-data" uv run python -m aggregator
```

Сервер разрешено слушать только на loopback. Это локальный инструмент без удалённой аутентификации, не публичный веб-сервис.

### Работа в браузере

1. Во «Входящих» укажите источник и загрузите один или несколько файлов.
2. Неизвестный формат откроется в мастере. Выберите листы и области, проверьте границы шапки и данных.
3. Для каждой колонки задайте целевое поле, `extra` либо исключение с причиной. Доказательство — точная цитата ячейки, например `B2="Артикул"`.
4. Явно выберите `replace_all`, `append` или `delta`, валюты и политики. Наличие четырёх строк само по себе не означает ни полный снимок, ни дельту.
5. Нажмите «Проверить первые 100 строк». Это не создаёт профиль или позиции.
6. После успешной проверки сохраните профиль. Полный разбор и переключение актуального снимка выполняются транзакционно.

Дальнейшие файлы того же источника с однозначно совпавшим fingerprint используют сохранённую ревизию. Неизвестный или неоднозначный формат снова требует решения оператора.
Автозамена всего каталога (`replace_all`) по совпадению fingerprint применяется только к файлу, который не уменьшает каталог: если разбор даёт меньше позиций, чем активный снимок, файл уходит в мастер с пометкой «замена уменьшит каталог» — дельта или полная замена выбирается явно.
Повторные байты не создают новые позиции и не возвращают указатель к прежнему снимку после отката.
Явное редактирование профиля сохраняет новую ревизию; старые профили, исходники и снимки остаются доступны.
Повторный разбор создаёт **неактивный** снимок; активация и откат меняют только указатель.
В разделе профилей доступен YAML выбранной ревизии; API: `/api/profiles/{id}/yaml?revision=1`.

### Реализованные механизмы

- XLSX, XLS через `xlrd`, CSV и безопасное извлечение ZIP; LibreOffice и модель для импорта не нужны.
- Ручное описание строковых, вертикальных, кросстаб-таблиц и нескольких областей; подсказки для Excel Table и именованных диапазонов.
- Политики скрытых строк, отрицательных/пустых цен, нескольких цен и валют, скрытой себестоимости, merged-ячеек и порога карантина.
- SQLite WAL; неизменяемые исходники в CAS по SHA-256; версии профилей, снимки поставок, построчный карантин, причины исключений и журнал действий.
- Каталог актуальных снимков с поиском, координатами и исходными значениями; история с активацией/откатом; `/health` и `/metrics`.
- Долговечный журнал заданий явных импортов (мастер и повторный разбор): прерванный процесс восстанавливается при следующем старте, повтор не дублирует снимок, у задания виден `retry_count`; API `/api/jobs`.
- Лимиты: 50 МиБ на файл, 200 МиБ на пакет и распакованные данные. XML/ZIP проверяются до открытия книги. Разбор сериализован внутри экземпляра приложения.
- Реестр обработчиков `aggregator/plugins.py` расширяет **формы таблиц**, а не список имён поставщиков.

### Проверка

```bash
uv run pytest tests -q
uv run python scripts/benchmark.py --rows 100000
uv run python scripts/measure_asvao.py
```

Проверены 34 регрессионных сценария: реальный ASVAO (7 874 позиции), ASVAO3, три «враждебных» прайса, варианты исполнения (включая V08/V15), защита листа, версии, откат, append/delta, карантин, журнал заданий и транзакционная конкуренция.
В реальном браузере: загрузка ASVAO → preview 100 → сохранение 7 874 позиций → поиск `06503163` с сохранённым ведущим нулём → YAML ревизии.
Замер полного импорта ASVAO на Apple M4 Max: **1,598 с, пик 83,14 МиБ**; 100 000 позиций: **17,182 с, пик 415,81 МиБ**; фоновый RSS сервера после импорта — 63,6 МБ. Это не сертификация производительности на четырёхъядерном сервере.
Матрица `acceptance_matrix.json`: **59 критериев подтверждены** тестами или замерами; 12 остаются `not_run` — 7 почтовых (адаптер не реализован) и 5 файловых без отдельных фикстур (пароль, файл без шапки, .xls, .xlsm, секреты в выводе).
Реальные прайсы поставщиков (`ASVAO.xlsx`, `ASVAO3.xlsx`) **не входят в репозиторий** — это чувствительные данные. Тесты на них (`test_G1_*`, полная загрузка) пропускаются при отсутствии файлов; локально при наличии копий проходят все 34 сценария.

### Границы поставки

Почтовый адаптер и PostgreSQL-backend **не реализованы**; LLM выключен и не требуется для ручного или повторного импорта.
Журнал заданий покрывает явные импорты из мастера и повторный разбор; автоимпорт защищён идемпотентностью по хэшу содержимого. Это не фоновый демон-очередь и не отдельные worker-процессы: упавшее задание ждёт следующего запуска приложения, а неудачное требует явного повтора.
Строгая статическая типизация всего Python-кода не заявлена. Проверка выполнения и приёмка — отдельны от диагностики LSP.
Полная матрица из 71 критерия находится в `acceptance_matrix.json`: непроверенные и неподдержанные сценарии не считаются пройденными.
Историческое архитектурное исследование ниже описывает также возможные модули и целевую инфраструктуру; это **не перечень уже реализованных возможностей**.

## 1. Настройка окружения проекта

### 1.1 Python LSP и Ruff LSP

В проект добавлен файл:

```text
.omp/lsp.json
```

Содержимое конфигурации:

```json
{
  "servers": {
    "basedpyright": {
      "command": "basedpyright-langserver",
      "args": ["--stdio"],
      "fileTypes": [".py", ".pyi"],
      "rootMarkers": [".omp", "pyproject.toml", "pyrightconfig.json", "setup.cfg", ".git"]
    },
    "ruff": {
      "command": "ruff",
      "args": ["server"],
      "fileTypes": [".py", ".pyi"],
      "rootMarkers": [".omp", "pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", ".git"],
      "isLinter": true
    }
  }
}
```

Причины выбора:

- В системе уже есть `basedpyright-langserver`, поэтому отдельный `pyright-langserver` не ставился.
- В системе уже есть `ruff 0.15.20`, поддерживающий `ruff server`.
- Проект изначально был XLSX-only и без стандартных Python root markers (`pyproject.toml`, `.git`, `ruff.toml`), поэтому в проектном `.omp/lsp.json` добавлен реальный marker `.omp`.
- Ruff помечен как linter-only через `isLinter: true`.

Проверено:

- `basedpyright (ready)`
- `ruff (ready)`
- smoke-проверка на временном `.py` файле показала символы Python и диагностику unused import от BasedPyright/Ruff.
- Временный файл после проверки удалён.

## 2. Факт-разбор Excel-файлов

Факт-разбор выполнялся через `/usr/bin/python3` и `openpyxl 3.1.5`; pandas не использовался как источник истины. Колонки и координаты брались только из ячеек.

### 2.1 ASVAO.xlsx

Файл: `ASVAO.xlsx`

Факты:

- SHA-256 prefix: `5b406e6db782a70b`
- Размер: `318766` bytes
- Лист: `TDSheet`
- Dimensions: `A1:E7878`
- Merge ranges: `A2:A4`, `B2:B4`, `C2:C4`, `D2:D4`
- Autofilter: отсутствует
- Freeze panes: отсутствует
- Hidden rows/cols: отсутствуют
- Formulas: отсутствуют
- Protection: `False`

Ключевые ячейки:

- `A1='name'`
- `E1='rub'`
- `A2='Производитель'`
- `B2='Артикул'`
- `C2='Номенклатура'`
- `D2='Количество'`
- `E2='Цена'`
- `E4='Цена (руб.)'`
- `B5='1132093J20'`
- `C5='ОПОРА ДВИГАТЕЛЯ'`
- `D5=4`
- `E5=2794`

Количество items по правилу файла:

```text
rows 5..7878, identity = B|C, qty = D, price = E → 7874 items
```

Важно: count не равен `max_row=7878`.

### 2.2 ASVAO3.xlsx

Файл: `ASVAO3.xlsx`

Факты:

- SHA-256 prefix: `a011c9b2e7d86ef1`
- Размер: `11896` bytes
- Листы: `TDSheet`, `Лист1`
- `TDSheet` openpyxl dimensions: `A1:G43`
- Реально populated bbox: `B3:G43`
- Merge ranges: `B4:B6`, `C4:C6`, `D4:D6`
- Autofilter: `B7:F7`, но строка 7 пустая и не является header row
- Freeze panes: отсутствует
- Hidden rows/cols: отсутствуют
- Formulas: отсутствуют
- Protection: `False`
- `Лист1` пустой

Ключевые ячейки:

- `F3='rub'`
- `B4='Артикул'`
- `C4='Номенклатура'`
- `D4='Количество'`
- `E5='размер'`
- `F4='Цена'`
- `G4='Сумма'`
- `F6='Цена (руб.)'`
- `G6='Цена (руб.)'`
- `B8='1132093J20'`
- `C8='ОПОРА ДВИГАТЕЛЯ'`
- `D8=4`
- `E8=1`
- `F8=2794`

Количество items по правилу файла:

```text
rows 8..43, identity = B|C, qty = D, price = F → 36 items
```

Важно: count не равен `max_row=43`.

### 2.3 Hostile fixtures 01–03

#### 01_ТехСнаб-Восток_прайс_с_ошибками.xlsx

Лист: `Прайс с 01.09`

Факты:

- Dimensions: `A1:I28`
- Header: `A8:I9`
- Autofilter: `A8:I8`
- Freeze panes: `A10`
- Hidden row: `14`
- Hidden col: `G`
- Formulas: `F26='=SUM(F10:F25)'`, `H26='=SUM(H10:H25)'`

Координаты planted errors / signals:

- `A1='ООО «ТехСнаб-Восток»  ИНН 7700123456  /  PRICE LIST  /  конфиденциально'`
- `A2='... Курсы: 1 EUR = 98,50 руб. ...'`
- `A5='ВНИМАНИЕ: колонка G скрыта (внутренняя себестоимость). Не удалять.'`
- `A8='№'`
- `B8='Код поставщика'`
- `F8='Цена'`
- `F9='опт, руб.'`
- `G8='себест'`
- `G10=800`
- `B14='TS-HIDDEN'`
- `C14='Ротор скрытый (hidden row) — позиция существует'`
- `F14='999,00'`
- `B16='0004451'`
- `F16='150 руб.'`
- `F17=None`
- `F18='-15'`
- `B19=None`
- `C20='Р'`
- `B22='Код поставщика'`
- `F22='Цена опт, руб.'`
- `C26='ИТОГО (не позиция)'`
- `F26='=SUM(F10:F25)'`
- `H26='=SUM(H10:H25)'`
- `A28='Цены с НДС 20%. Отрицательная цена — корректировка. Пустая цена = под заказ.'`

Intended candidate item rows: `10–20` + `23–25` = 14, до применения P-политик.

#### 02_HONGXING_TOOLS_spare_parts_USD.xlsx

Лист: `Sheet1`

Факты:

- Dimensions: `A1:G20`
- Две таблицы: `rows 5–13` и `rows 18–20`

Координаты:

- `A1='HONGXING TOOLS CO., LTD  // Spare parts for power tools  // EXW Ningbo'`
- `B2=datetime.datetime(2026, 9, 1, 0, 0)`
- `D2=45901`
- `A3='Currency: USD. Колонка F = штрихкод, не число.'`
- `A5='Item No.'`
- `F5='Barcode'`
- `A6=1234`
- `F6=4800123456789`
- `A7='001234'`
- `F7='4800123456789'`
- `A8=4451000123`
- `F8=460712345678`
- `A17='DISCONTINUED / снято с производства — вторая таблица на том же листе, другие колонки'`
- `A18='sku'`
- `C18='price_rub'`
- `A19='OLD-01'`
- `C19=90`

Intended items: 8 + 2 = 10 при P4=parse-all.

#### 03_МегаИнструмент_1С_выгрузка_враждебная.xlsx

Лист: `TDSheet`

Факты:

- Dimensions: `A1:K25`
- Hidden col: `B`
- Protection: `True`
- Autofilter: `C7:K7`
- Formulas: `I19='=SUM(I8:I18)'`, `J19='=SUM(J8:J18)'`

Координаты:

- `A1='Прайс-лист'`
- `C2='Выгрузка № 17-44 от 11.09.2026   Организация: ИП Сидоров'`
- `C3='rub'`
- `C4='Производитель'`
- `D4='Артикул'`
- `E4='Штрих-код'`
- `F4='Номенклатура'`
- `G4='Количество'`
- `H5='в резерве'`
- `I4='Цена'`
- `I5='закуп'`
- `J5='розн'`
- `K4='Кратность / фасовка'`
- `D8='1 609 203 243'`
- `D9='1609203243'`
- `E8='3165140589411'`
- `G8=12`
- `H8=0`
- `I8=450`
- `J8=690`
- `K8='2'`
- `F19='Итого'`
- `I19='=SUM(I8:I18)'`
- `C20='Гарантия 14 дней. Позиции «под заказ» не резервировать. Кратность обязательна.'`
- `C24='Артикул'`
- `E25=500`

Intended candidate item rows: `8–18` + `25` = 12, subject to P3/P4 decisions.

## 3. Выбранная архитектура v1

Победитель: deterministic core `эвристики + YAML-профили + wizard`.

Основной поток:

```text
Email/Ingest
  → RawStore CAS
  → FileNormalize/Security
  → DetectLayout/Fingerprint
  → MapColumns/ProfileResolver
  → ParseRows
  → NormalizeValidate
  → CanonicalPersist/Shipment
  → Quarantine/Review UI
```

Принципы:

- Email module не знает parser.
- Parser не знает email.
- Raw artifact immutable.
- DetectLayout отдельно от MapColumns.
- Fingerprint не включает sheet name как exact key.
- Known fingerprint → zero-click.
- Unknown/ambiguous → wizard/profile.
- Reprocess всегда создаёт новый shipment.
- Current catalog = pointer to shipment, не UPDATE строк.
- LLM не участвует в парсинге строк.

## 4. Каталог вариантов по слоям

| Слой | Варианты | Winner v1 | Отвергнуто |
|---|---|---|---|
| Почта | IMAP poll; IMAP IDLE; Graph API; локальный Maildir/spool | IMAP poll или локальный spool adapter | parser внутри email handler; скачивание по ссылкам по умолчанию |
| Blob/raw | CAS FS; MinIO/S3; PostgreSQL BYTEA; NFS | CAS filesystem by SHA-256 + DB index | BYTEA для всех xlsx; unique by filename |
| Очередь | Postgres SKIP LOCKED; Redis Streams; RabbitMQ/NATS; filesystem queue | PostgreSQL job table + lease/heartbeat/outbox | in-memory queue; Redis/Rabbit as default без нагрузки |
| XLS conversion | native reader; LibreOffice; xlrd/BIFF; reject legacy | magic-detect + FileNormalize; soffice concurrency=1 | LibreOffice как основной parser |
| DetectLayout | native Table; named range; autofilter candidate; header scoring; vertical; islands; crosstab plugin | Table → named range → profile range → scored header → vertical/islands → review | autofilter as truth; sheet name exact |
| Fingerprint | header hash; header+offset+n_cols; +merge shape; +value signatures | header+offset+n_cols+header_row+merge/value signatures | filename/From/sheet required key |
| MapColumns | YAML exact; wizard; synonym ranker; LLM suggestion | YAML + wizard; optional ranker | silent nearest profile |
| Parse | full DOM; probe→stream; calamine values + openpyxl metadata; plugin | metadata probe + chunked value stream | `просто df` без provenance |
| Quarantine | file; row; sheet/table card; dead-letter | distinct scopes | one generic failed flag |
| Store | normalized rows only; canonical+raw_row; EAV; document DB | typed canonical + jsonb evidence | JSON dump only; dropping unknown cols |
| UI | YAML-only; web wizard; Streamlit; admin dashboard | web wizard + profile registry | Streamlit as product shell |
| Isolation | same process; workers; cgroup; container | worker process + cgroup; soffice isolated | untrusted workbook in web process |
| Micro-LLM | none; ranker; 1–3B; 7B Q4; external API | off by default; suggestion only | row parsing; autonomous writes |

## 5. Политики P1–P11

| P | Развилка | Выбор v1 |
|---|---|---|
| P1 | hidden row with article | include + `flags.hidden_row` |
| P2 | negative price | item + `flags.neg_price` |
| P3 | two prices row | N items by `price_kind` |
| P4 | second table/island | parse all profiled islands; unknown → wizard |
| P5 | empty price | `price=NULL` + status/availability |
| P6 | hidden cost | drop_with_reason, not extra |
| P7 | full/append/delta current | explicit `ingest_mode` required |
| P8 | currency columns | N items by currency |
| P9 | multiple valid sheets | approved profile parse_all; unknown master-per-sheet |
| P10 | crosstab | plugin/unpivot only |
| P11 | zero data rows | quarantine file |

Ключевой вывод: `UNIQUE(article)` запрещён. После P3 uniqueness зависит от expanded dimensions: `shipment_id`, `table_idx`, `source_row`, `price_kind`, `currency`, `pack`.

Delta semantics for P7:

- `replace_all`: new shipment becomes full current snapshot after successful validation.
- `append`: new shipment adds rows but does not delete absent old rows; use only for explicitly append-only sources.
- `delta`: every row must carry explicit operation semantics or profile/source rule (`upsert`, `delete`, `no_change`). If delta mode is missing or ambiguous, file goes to review/quarantine; row count alone never decides mode.
- Current pointer moves only after the full shipment/delta patch is validated and committed.

## 6. Версионирование

| Ось | Смысл |
|---|---|
| `V_file` | immutable blob + SHA-256 |
| `V_inbound` | письмо/attachment/replay identity |
| `V_profile` | `profile_id + profile_rev`; старые shipments остаются на старом rev |
| `V_ship` | `(source_id, ship_n)` immutable; current = pointer |

Правила:

- fingerprint = layout id, не версия склада;
- reprocess → new shipment;
- rollback → смена pointer;
- UPDATE price на месте запрещён.

## 6.1 Traceability: L1–L14 и C1–C16

### L-инварианты

| ID | Инвариант | Где проверяется |
|---|---|---|
| L1 | inbound → N files → N jobs | email integration tests, multi-attachment cases |
| L2 | SHA-256 уникален; replay не плодит items | V25/no-extension copy, repeat hash tests |
| L3 | fingerprint → one profile / unknown / ambiguous | ASVAO vs ASVAO3 vs V07, V15, V26 |
| L4 | parse only DetectLayout range | ASVAO counts, ASVAO3 empty autofilter row, totals/repeated headers |
| L5 | uniqueness only after P3/P8 expansion; quarantine keeps raw_row | V03, V16, V06 C8 |
| L6 | file/row/sheet/table statuses do not silently overlap | V14 file quarantine, V06 row quarantine, V13 sheets |
| L7 | current_shipment_id + P7; items immutable | V01→V02→V08, rollback |
| L8 | every source column is canonical XOR extra XOR drop(reason) | P6 hidden cost, extra columns |
| L9 | article/OEM/barcode text on whole path | HONGXING numeric barcode, V06/V07 identifiers |
| L10 | wizard atomic: probe rows accepted all-or-nothing | V15 wizard dry-run |
| L11 | IMAP secrets nowhere | log/UI/config security tests |
| L12 | second table = P4 | V05, V22 |
| L13 | LLM never writes items | V15 LLM suggestion tests |
| L14 | LLM off = no slot | V15 with LLM disabled |

### C-инварианты

| ID | Case | Expected |
|---|---|---|
| C1 | duplicate SKU | keep two rows/items, no UNIQUE(article) |
| C2 | two article spellings | preserve both raw texts; matching is downstream |
| C3 | one SKU, two packings | distinct items keyed with pack/multiplicity |
| C4 | hidden row | resolved by P1 include+flag |
| C5 | total row | drop as non-item with reason |
| C6 | repeated header | drop as non-item with reason |
| C7 | empty brand | valid nullable brand |
| C8 | empty article and name | row quarantine with raw_row |
| C9 | rollback + replay | pointer rollback; replay idempotent |
| C10 | ASVAO profile on ASVAO3/V07 | fingerprint miss/review |
| C11 | extra/drop on repeat | same disposition on replay |
| C12 | two price lists + PDF | independent jobs/statuses |
| C13 | crash parse→store | retry without duplicate/current partial |
| C14 | two master cards | table/island cards independent |
| C15 | low-confidence LLM | no auto-accept |
| C16 | YAML change | new profile_rev/new ship; old ship unchanged |

## 6.2 Строгий порядок pipeline

1. `Email/Ingest` сохраняет только inbound/attachment metadata и stream.
2. `RawStore` создаёт immutable blob и `file_receipt`.
3. `FileNormalize` делает security/magic/conversion boundary.
4. `DetectLayout` находит sheet/table/range/fingerprint, но не мапит колонки.
5. `MapColumns/ProfileResolver` выбирает profile или создаёт wizard/review card.
6. `ParseRows` читает только утверждённый диапазон DetectLayout.
7. `NormalizeValidate` применяет P-политики, quarantine и canonical staging.
8. `CanonicalPersist` атомарно создаёт immutable shipment и двигает current pointer.

Перестановка этих шагов запрещена: например, MapColumns до DetectLayout ведёт к overfit; ParseRows до range detection ведёт к `max_row`-ошибкам; Persist до полной валидации создаёт partial current.

## 7. Канон строки

Минимальный canonical item:

```text
supplier_id/source_id,
source_file_id,
source_sheet,
table_idx,
source_row,
article TEXT,
oem TEXT,
barcode TEXT,
brand,
name,
name_raw,
qty,
qty_raw,
stock,
availability_raw,
price,
price_kind,
currency,
vat,
pack,
multiplicity,
min_qty,
uom,
extra jsonb,
raw_row jsonb,
flags jsonb,
ingested_at,
parsed_at,
shipment_id,
profile_rev,
schema_rev
```

Обязательные инварианты:

- `article`, `oem`, `barcode` — text на всём пути;
- ведущие нули сохраняются;
- лишние колонки → `extra` или `drop_with_reason`, не молча;
- quarantine содержит `raw_row` и координаты.

## 8. DDL skeleton

Псевдо-DDL PostgreSQL, не файл `schema.sql`:

```sql
source(
  source_id pk,
  source_key unique not null,
  display_name not null,
  status,
  created_at
);

inbound_message(
  inbound_id pk,
  account_id not null,
  folder not null,
  uidvalidity text,
  uid text,
  message_id text,
  received_at,
  unique(account_id, folder, uidvalidity, uid)
);

source_file(
  file_id pk,
  source_id fk,
  content_sha256 text not null,
  original_name text not null,
  size_bytes bigint,
  detected_format text,
  storage_uri text not null,
  file_status text,
  unique(source_id, content_sha256)
);

file_receipt(
  file_receipt_id pk,
  file_id fk source_file,
  inbound_id fk inbound_message,
  attachment_part text not null,
  original_name text not null,
  received_at timestamptz,
  unique(inbound_id, attachment_part),
  unique(file_id, inbound_id, attachment_part)
);

-- source_file дедуплицирует blob по hash; file_receipt сохраняет все повторы того же blob
-- из разных писем/пересылок. Нельзя хранить только один inbound_id внутри source_file.

layout_profile(
  profile_id pk,
  source_id fk,
  fingerprint_version int not null,
  fingerprint_hash text not null,
  profile_rev int not null,
  mapping_json jsonb not null,
  profile_status text,
  created_at,
  unique(source_id, fingerprint_hash, profile_rev)
);

ingest_shipment(
  shipment_id pk,
  source_id fk,
  file_id fk,
  profile_id fk,
  profile_rev int not null,
  shipment_seq int not null,
  parent_shipment_id fk null,
  ingest_mode text not null check (ingest_mode in ('replace_all','append','delta')),
  p3_mode text not null check (p3_mode in ('n_items','extra_prices')),
  shipment_status text not null,
  created_at,
  unique(source_id, shipment_seq)
);

source_current(
  source_id pk,
  shipment_id unique not null,
  changed_at
);

shipment_table(
  shipment_id fk,
  table_idx int not null,
  sheet_index int not null,
  sheet_name text not null,
  region_ref text,
  header_row int,
  data_start_row int,
  layout_origin text,
  table_status text,
  primary key(shipment_id, table_idx)
);

shipment_row(
  shipment_id fk,
  table_idx int not null,
  source_row int not null,
  is_hidden bool default false,
  row_status text not null,
  raw_row jsonb not null,
  flags jsonb not null default '{}',
  primary key(shipment_id, table_idx, source_row)
);

canonical_item(
  item_id pk,
  shipment_id fk,
  table_idx int not null,
  source_row int not null,
  article text,
  oem text,
  barcode text,
  brand text,
  name text,
  name_raw text,
  qty numeric,
  qty_raw text,
  stock numeric,
  availability_raw text,
  price numeric null,
  price_kind text not null,
  currency text not null default 'UNK',
  vat text,
  pack text,
  multiplicity numeric,
  min_qty numeric,
  uom text,
  extra jsonb not null default '{}',
  raw_row jsonb not null,
  flags jsonb not null default '{}',
  ingested_at timestamptz,
  parsed_at timestamptz,
  profile_rev int not null,
  schema_rev int not null
);

quarantine_issue(
  issue_id pk,
  scope text check (scope in ('file','sheet','table','row','job')),
  file_id fk,
  shipment_id fk null,
  table_idx int null,
  source_row int null,
  code text not null,
  severity text not null,
  raw_row jsonb,
  evidence jsonb not null,
  status text,
  created_at
);
```

P3 N-items unique:

```sql
-- PostgreSQL: expression index, not table constraint, because pack can be NULL.
create unique index canonical_item_p3_n_items_uidx
  on canonical_item (
    shipment_id,
    table_idx,
    source_row,
    price_kind,
    currency,
    coalesce(pack, '')
  );
```

Запрещено:

```sql
unique(article)
unique(file_id, article)
unique(filename, sha256)
```

## 9. YAML profile drafts with quotes

### 9.1 ASVAO profile

```yaml
profile_id: asvao_td_a
profile_rev: 1
fingerprint:
  exact_key_excludes: [sheet_name, filename, email_from]
  components:
    header_row: 2
    header_rows: [2, 3, 4]
    data_start_row: 5
    column_offset: A
    n_cols: 5
    merged_ranges: ["A2:A4", "B2:B4", "C2:C4", "D2:D4"]
    header_quotes:
      A2: "A2='Производитель'"
      B2: "B2='Артикул'"
      C2: "C2='Номенклатура'"
      D2: "D2='Количество'"
      E2: "E2='Цена'"
      E4: "E4='Цена (руб.)'"
currency:
  value: RUB
  quote: "E1='rub'"
tables:
  - table_idx: 1
    sheet_selector:
      optional_regex: "^TDSheet$"
      quote: "sheet observed as TDSheet, not fingerprint key"
    range:
      header_rows: [2, 3, 4]
      data_start_row: 5
      columns:
        brand:
          col: A
          quote: "A7878='NACHI'"
        article:
          col: B
          quote: "B5='1132093J20'"
          type: text
        name:
          col: C
          quote: "C5='ОПОРА ДВИГАТЕЛЯ'"
        qty:
          col: D
          quote: "D5=4"
        price:
          col: E
          quote: "E5=2794"
          price_kind: unknown
          price_kind_quote: "E2='Цена'; E4='Цена (руб.)' — вид цены opt/rrc не подтверждён"
          currency: RUB
```

### 9.2 ASVAO3 profile

```yaml
profile_id: asvao_td_b
profile_rev: 1
fingerprint:
  exact_key_excludes: [sheet_name, filename, email_from]
  components:
    header_row: 4
    header_rows: [4, 5, 6]
    data_start_row: 8
    column_offset: B
    n_cols: 6
    autofilter_candidate:
      ref: "B7:F7"
      quote: "autofilter B7:F7 is on empty row 7, not header"
      use_as_header: false
    merged_ranges: ["B4:B6", "C4:C6", "D4:D6"]
    header_quotes:
      B4: "B4='Артикул'"
      C4: "C4='Номенклатура'"
      D4: "D4='Количество'"
      E5: "E5='размер'"
      F4: "F4='Цена'"
      G4: "G4='Сумма'"
      F6: "F6='Цена (руб.)'"
currency:
  value: RUB
  quote: "F3='rub'"
tables:
  - table_idx: 1
    sheet_selector:
      optional_regex: "^TDSheet$"
      quote: "sheet observed as TDSheet, not fingerprint key"
    range:
      header_rows: [4, 5, 6]
      data_start_row: 8
      columns:
        article:
          col: B
          quote: "B8='1132093J20'"
          type: text
        name:
          col: C
          quote: "C8='ОПОРА ДВИГАТЕЛЯ'"
        qty:
          col: D
          quote: "D8=4"
        extra.size:
          col: E
          quote: "E5='размер'; E8=1"
        price:
          col: F
          quote: "F8=2794"
          price_kind: unknown
          price_kind_quote: "F4='Цена'; F6='Цена (руб.)' — вид цены opt/rrc не подтверждён"
          currency: RUB
        extra.sum:
          col: G
          quote: "G4='Сумма'; G8=None"
```

### 9.3 YAML/profile validation rules

Every profile saved by UI or edited manually must pass validation:

- every mapped canonical column has `col`/cell reference and `quote`;
- every `extra.*` mapping has `quote`;
- every `drop_with_reason` column has source coordinate/header quote and reason;
- `sheet_selector` may be a hint, but sheet name cannot be an exact fingerprint key;
- `price_kind` must be `unknown` unless there is a quoted header/value proving `opt`, `rrc`, `закуп`, `розн`, etc.;
- profile save creates a new immutable `profile_rev`; old shipments keep their original `profile_rev`;
- YAML without required quotes is invalid and cannot become active.

## 10. Web UI: всё, что политика/режим — настройка

Принцип: если настройка влияет на ingest, она видна и управляема в web UI. YAML/DB — хранилище, не основной интерфейс оператора.

### 10.1 Настройки UI

- Почта: IMAP, folders, poll/IDLE, filters, dedup, allowed attachments.
- Supplier/source: aliases, default currency/VAT, active profiles.
- Policies P1–P11.
- Fingerprint components and thresholds.
- Wizard defaults.
- LLM slot enable/disable/model/timeout/threads/confidence.
- Resource caps: workers, RSS, file size, row limit, unzip ratio, retries, timeouts.
- Ingest mode: replace_all / append / delta / ask.

### 10.2 Контроль UI

- Queue status.
- Last ingests.
- Shipment list/current pointer.
- Diff shipments.
- Rollback.
- Quarantine file/row/sheet cards.
- Raw preview vs canonical preview.
- Health: CPU/RSS/disk/DB/soffice.
- Reprocess with new profile_rev.

### 10.3 Safety rails, не настройки

- Raw immutable.
- Old shipments immutable.
- Reprocess creates new shipment.
- `article/oem/barcode` text.
- No `UNIQUE(article)`.
- Sheet name not exact fingerprint key.
- LLM never writes items.
- Secrets never in YAML/logs/HTML.
- Macro execution forbidden.

### 10.4 Auth/RBAC and operator workflow

Minimal RBAC:

- `viewer`: read shipments, logs, metrics and quarantine evidence;
- `operator`: resolve quarantine, run wizard dry-runs, request reprocess;
- `profile_admin`: approve/save profile revisions and P-policy changes;
- `admin`: configure mail sources, secrets references, resource caps and LLM slot.

State-changing actions require audit fields: `operator_id`, reason/comment, previous value, new value, timestamp and request id. Dangerous actions (`rollback`, LLM enable, profile activation, changing P7 ingest mode) require confirmation and are reversible by pointer/profile revision, not by mutating old rows.

## 11. Micro-LLM slot

Default: disabled.

Input:

```json
{
  "request_id": "...",
  "schema_version": "llm-map-v1",
  "headers": [
    {"cell": "A1", "value": "Код"},
    {"cell": "D1", "value": "Ст"},
    {"cell": "E1", "value": "Пр"}
  ],
  "sample_rows": [
    [{"cell": "A2", "value": "AM-01"}, {"cell": "D2", "value": 180}]
  ],
  "allowed_targets": ["article", "name", "qty", "price", "currency", "brand"],
  "policies": {"p3_mode": "n_items"}
}
```

Output suggestion only:

```json
{
  "status": "map|ambiguous|reject|disabled|error",
  "confidence": 0.0,
  "columns": [
    {
      "target": "article",
      "source_cell": "A1",
      "header_value": "Код",
      "evidence": ["A2='AM-01'"]
    }
  ],
  "ask_human": ["Ст could be status or price"],
  "rationale": "..."
}
```

Rules:

- LLM не парсит строки.
- LLM не пишет items.
- LLM не блокирует ingest.
- LLM off = нет слота.
- External API только для headers + 3–5 sample rows и только с privacy approval.

## 12. Логирование

Логи — structured JSON.

Общие correlation fields:

```json
{
  "run_id": "...",
  "inbound_id": "...",
  "file_id": "...",
  "source_id": "...",
  "shipment_id": "...",
  "profile_id": "...",
  "profile_rev": 1,
  "fingerprint_hash": "...",
  "job_id": "...",
  "table_idx": 1,
  "source_sheet": "..."
}
```

Обязательные events:

- `inbound.received`
- `raw.stored`
- `file.normalized`
- `file.normalize_failed`
- `layout.detected`
- `profile.matched`
- `profile.ambiguous`
- `rows.parsed`
- `rows.normalized`
- `row.quarantined`
- `shipment.committed`
- `current.rollback`
- `profile.saved`
- `llm.suggestion_created`

Уровни:

- DEBUG: detector/cell-level details, temporary.
- INFO: stage transitions/counts.
- WARN: quarantine/retry/ambiguous.
- ERROR: failed job/converter/DB.
- AUDIT: operator actions/profile changes/rollback/LLM enable.

Нельзя логировать:

- IMAP password / OAuth token.
- Полный email body по умолчанию.
- Массовые raw rows в log stream.
- Full LLM prompt/output with commercial rows.
- Secrets in HTML preview.

Log schema rules:

- Each log event has `schema_version`.
- Retention differs by stream: operational logs can rotate aggressively; audit/quarantine evidence follows client retention policy.
- Redaction is applied before log write, not only in UI.
- DEBUG cell-level logs are opt-in per run and time-limited.

## 13. Метрики

Prometheus-compatible `/metrics`.

Metric rules:

- Metric names and label sets are versioned with the application.
- Labels must be low-cardinality: no filename, full sha256, Message-ID, raw email, source row, or free-text reason as labels.
- `source_id`, `profile_id`, `stage`, `status`, `reason_code`, `worker_type`, `model_id` are allowed if cardinality is bounded.
- Full evidence, coordinates and raw values belong in DB/quarantine records, not metric labels.

### Pipeline

```text
ingest_inbound_total
ingest_files_total{format,status}
ingest_shipments_total{source_id,status,ingest_mode}
ingest_rows_total{source_id,result}
ingest_items_total{source_id}
```

### Durations

```text
ingest_stage_duration_seconds{stage}
```

Stages:

- `mail_fetch`
- `raw_store`
- `file_normalize`
- `detect_layout`
- `map_columns`
- `parse_rows`
- `normalize_validate`
- `persist_shipment`
- `wizard_dry_run`
- `llm_suggestion`

### Queue

```text
ingest_jobs_queued{stage}
ingest_jobs_running{stage}
ingest_jobs_retry_wait{stage}
ingest_jobs_failed_total{stage,reason}
ingest_job_attempts_total{stage}
ingest_job_oldest_age_seconds{stage}
ingest_job_lease_expired_total{stage}
```

### Quarantine

```text
ingest_quarantine_files_total{reason}
ingest_quarantine_rows_total{reason}
ingest_quarantine_open{scope,reason}
ingest_quarantine_resolution_total{action}
```

### Layout/profile

```text
ingest_fingerprint_hits_total{source_id,profile_id}
ingest_fingerprint_misses_total{source_id,reason}
ingest_profile_ambiguous_total{source_id}
ingest_profile_revision_total{source_id,profile_id}
ingest_sheet_name_used_as_exact_key_total
```

`ingest_sheet_name_used_as_exact_key_total` должен оставаться 0.

### Data quality

```text
ingest_missing_article_total{source_id}
ingest_missing_name_total{source_id}
ingest_null_price_total{source_id}
ingest_negative_price_total{source_id}
ingest_duplicate_article_total{source_id}
ingest_hidden_rows_included_total{source_id}
ingest_hidden_columns_dropped_total{source_id}
ingest_repeated_headers_dropped_total{source_id}
ingest_total_rows_dropped_total{source_id}
```

### Resource / LibreOffice / LLM

```text
process_resident_memory_bytes{worker_type}
ingest_worker_peak_rss_bytes{stage}
ingest_temp_disk_bytes
ingest_soffice_jobs_total{status}
ingest_soffice_running
ingest_soffice_zombie_total
ingest_soffice_timeout_total
ingest_llm_requests_total{status,model}
ingest_llm_duration_seconds{model}
ingest_llm_auto_accept_total
```

For v1, `ingest_llm_auto_accept_total` should be 0.

## 14. Alerts

Minimum alerts:

- Queue stuck.
- High quarantine ratio.
- Unknown layouts spike.
- Row bad ratio > 15%.
- No successful ingest for expected source interval.
- LibreOffice stuck/zombie.
- Disk low.
- Worker RSS > cap.
- DB deadlocks/retries spike.
- External LLM enabled unexpectedly.

## 15. Тестовая стратегия

### 15.1 Unit tests

- Price parser: `1 240,50`, `150 руб.`, NBSP, empty, negative.
- Qty parser: `много`, `нет`, `<5`, `под заказ`, `N/A`.
- ID parser: leading zeros, long barcode, scientific notation.
- Fingerprint: same sheet name different layout; filename/From not exact key.
- P1–P11 policies.

### 15.2 Fixture tests

- ASVAO count = 7874.
- ASVAO3 count = 36.
- ASVAO/ASVAO3/V07 all `TDSheet` but separate fingerprints.
- TechSnab hidden row/hidden cost/repeated header/total row.
- HONGXING numeric barcode/article preserved as text.
- Mega protection ≠ encryption, two article spellings preserved.
- V01→V02 same fingerprint new shipment.
- V08 explicit delta required.
- V14 zero rows = file quarantine.
- V15 ambiguous = wizard.
- V21 P1×P3 counts multiply.

### 15.3 Integration tests

- 0 attachments.
- 1 xlsx.
- 3 xlsx.
- xlsx + PDF.
- zip with Cyrillic filename.
- forwarded email changes From.
- repeat Message-ID.
- repeat hash + new Message-ID.
- NDR/bounce.
- winmail.dat.
- attachment without extension.

### 15.4 Crash/idempotency tests

- Crash after raw store before metadata.
- Crash after metadata before detect.
- Crash mid-parse chunk.
- Crash after staging before shipment commit.
- Crash after commit before current pointer update.
- Concurrent retry same job.

Expected:

- no duplicate canonical items;
- no partial current;
- old current remains valid;
- retries idempotent.

### 15.5 UI tests

- Wizard saves profile only with valid preview.
- YAML requires quotes for mapped columns.
- Sheet name cannot be exact fingerprint key.
- Operator can rollback current shipment.
- Operator can reprocess with new profile_rev.
- Quarantine card shows coordinates/raw/reason/action.
- Secrets not rendered in HTML.
- LLM suggestion is draft, not applied.

### 15.6 Observability tests

- Every job emits start and terminal event.
- Shipment commit emits counts.
- Quarantine increments metric.
- Profile save emits audit event.
- Rollback emits audit event.
- Logs contain correlation IDs.
- Logs do not contain IMAP secrets.
- `/metrics` exposes queue depth.
- `soffice` timeout increments metric.

## 16. RAM/CPU smета

Assumptions:

- Total RAM: 20 GB.
- OS reserve: ≥4 GB.
- Safety reserve: ≥2 GB.
- App practical ceiling: about 14 GB.

| Scenario | Estimate |
|---|---|
| Simple XLSX | <1 GB expected with chunking |
| ASVAO ~7874 rows | <1 GB expected; benchmark required |
| 100k rows | 1–4 GB expected with bounded chunks |
| openpyxl full object model | may inflate 10–50× compressed size; not primary path |
| 2 parser workers | upper bound 2–8 GB depending width |
| LibreOffice | 1–2 GB; concurrency=1 |
| LLM off | 0 model RSS; default |
| embeddings/ranker | 100–400 MB acceptable |
| 1–3B Q4 | possible as suggestion slot |
| 7B Q4/INT4 | conditionally fits with concurrency=1 and benchmark |
| 7B INT8 | not safe as default |
| 7B FP16 | rejected for 20 GB |

If actual machine has 28 GB RAM, 7B slot must be recalculated separately.

## 17. Anti-overfit rules

Do not hardcode:

1. `sheet == TDSheet`.
2. `header_row == 2` or `data_start == 5`.
3. Table always starts at column A.
4. Column B always article, column A always brand.
5. Exactly 5 columns.
6. Currency always from `E1` or `F3`.
7. `auto_filter.ref` equals header row.
8. `article` already string in Excel.
9. One supplier = one fingerprint.
10. ASVAO/ASVAO3 as universe of formats.

## 18. Blocking client questions

1. Server is exactly 20 GB RAM or actually 28 GB? This affects 7B slot.
2. `.xlsm`: read data-only or always quarantine?
3. Is external LLM API allowed for headers + 3–5 sample rows only?
4. Default `ingest_mode`: replace_all, append, delta, or ask?
5. Default P1: include hidden valid rows or skip?
6. Negative prices: adjustment, error, or discount?
7. How to assign `supplier_id`: email/domain/manual/INN/cabinet?
8. Retention period for raw/quarantine/evidence?

## 19. v1 acceptance checklist

v1 is not acceptable without:

- structured JSON logs with correlation IDs;
- `/metrics` endpoint;
- queue/quarantine/shipment metrics;
- audit logs for profile changes and rollback;
- ASVAO count 7874;
- ASVAO3 count 36;
- V07 not ASVAO/ASVAO3;
- V14 file quarantine;
- V03 P3 uniqueness;
- V08 explicit delta mode;
- replay same hash no duplicates;
- crash before commit no partial current;
- UI per-file timeline and count breakdown;
- no secrets in logs/UI.
