# Metal Accounting — Учёт металла

## Purpose

Единый контур учёта металла мастерской: хранилища, документы движений (receipt/transfer/writeoff/remelt), остатки по хранилищам и сплавам. Интегрируется с заказами ремонта, фиксирует потери металла и поддерживает ведомость остатков.

Модуль: `jewelry_metal_accounting`

Исторические ТЗ: `METAL_ACCOUNTING_SPEC.md`, `METAL_ACCOUNTING_FLOW_SPEC.md`

## Ключевые модели

### jewelry.metal.storage — Хранилище металла

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название |
| code | Char | Код (уникален по компании) |
| active | Boolean | Активно |
| company_id | Many2one | Компания |
| responsible_user_id | Many2one (res.users) | Ответственный |
| notes | Text | Примечания |

### jewelry.metal.document — Документ движения металла

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Номер (авто из последовательности) |
| operation_type | Selection | receipt / transfer / writeoff / remelt (тип операции по умолчанию для строк) |
| state | Selection | draft / posted / cancel |
| document_date | Datetime | Дата документа |
| partner_id | Many2one (res.partner) | Контрагент |
| company_id | Many2one | Компания |
| source_storage_id | Many2one (jewelry.metal.storage) | Хранилище-источник (для всех строк) |
| dest_storage_id | Many2one | Хранилище-приёмник (для всех строк) |
| repair_order_id | Many2one (jewelry.repair.order) | Связанный заказ (только auto-created) |
| source_operation_id | Many2one (jewelry.repair.order.operation) | Операция-источник |
| source_ref | Char | Ссылка на источник |
| notes | Text | Примечания |
| line_ids | One2many | Строки |
| move_ids | One2many | Движения (создаются при проведении) |
| log_ids | One2many | Журнал событий |
| amount_total | Monetary | Информационная сумма (только для receipt) |
| has_negative_balance_impact | Boolean | Предупреждение: транзакция уведёт баланс в минус |

### jewelry.metal.document.line — Строка документа

| Поле | Тип | Описание |
|------|-----|----------|
| document_id | Many2one | Документ |
| operation_type | Selection | receipt / transfer / writeoff / remelt |
| sequence | Integer | Порядок |
| alloy_id | Many2one (jewelry.metal.alloy) | Входной сплав |
| weight | Float | Входной вес (г) |
| rate_datetime | Datetime | Дата котировки (для receipt) |
| rate_price_per_gram | Monetary | Котировка (авто, только receipt) |
| amount | Monetary | Информационная сумма (авто, только receipt) |
| output_alloy_id | Many2one | Выходной сплав (только remelt) |
| output_weight | Float | Выходной вес (только remelt) |
| loss_weight | Float | Потеря при плавке (только remelt) |
| conversion_ratio | Float | Коэффициент конверсии (только remelt) |
| source_storage_id | Many2one | Хранилище-источник (переопределяет уровень документа) |
| dest_storage_id | Many2one | Хранилище-приёмник (переопределяет уровень документа) |
| source_storage_balance | Float | Текущий баланс источника |
| source_storage_balance_after | Float | Прогноз баланса источника после операции |
| dest_storage_balance | Float | Текущий баланс приёмника |
| dest_storage_balance_after | Float | Прогноз баланса приёмника после операции |
| source_material_line_id | Many2one | Строка материала (для auto-created) |
| notes | Text | Примечания |

### jewelry.metal.move — Запись движения

Создаётся автоматически при проведении документа. Хранит weight_in, weight_out, signed_weight (= weight_in − weight_out), running_balance.

| Поле | Тип | Описание |
|------|-----|----------|
| document_id | Many2one | Документ |
| alloy_id | Many2one | Сплав |
| storage_id | Many2one | Хранилище |
| operation_type | Selection | Тип операции |
| weight_in / weight_out | Float | Вес прихода/расхода |
| signed_weight | Float | weight_in − weight_out |
| running_balance | Float | Накопительный баланс после этой записи |
| state | Selection | posted / cancel |
| document_date | Datetime | Дата документа |

### jewelry.metal.document.log — Журнал событий документа

Фиксирует: create, write, post, cancel, reset_to_draft с пользователем и временем.

### jewelry.metal.loss — Запись потери металла

Создаётся автоматически при завершении операции, если у материальной строки есть weight_loss.

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Референс (авто) |
| loss_date | Datetime | Дата |
| loss_type | Selection | material / recoverable / irrecoverable / setting |
| alloy_id | Many2one | Сплав |
| weight_loss | Float | Вес потери (г) |
| storage_id | Many2one | Хранилище исполнителя |
| source_operation_id | Many2one | Операция |
| source_repair_order_id | Many2one | Заказ (через операцию) |
| source_material_line_id | Many2one | Строка материала |

### jewelry.metal.stock.statement.wizard — Ведомость остатков (Transient)

| Поле | Тип | Описание |
|------|-----|----------|
| period_preset | Selection | today / this_week / this_month / last_month / this_year / custom |
| date_from / date_to | Date | Период |
| storage_ids | Many2many | Фильтр по хранилищам |
| alloy_ids | Many2many | Фильтр по сплавам |
| include_zero_lines | Boolean | Включить нулевые строки |
| line_ids | One2many | Результат (transient) |

### jewelry.repair.executor (расширение)

Добавляется поле `metal_storage_id` — хранилище металла по умолчанию для исполнителя.

### jewelry.repair.order.operation (расширение)

Добавляются:
- `executor_metal_storage_id` — вычислено из executor.metal_storage_id
- `metal_writeoff_document_ids` — write-off документы, созданные из операции
- `metal_loss_ids` — записи потерь, созданные при завершении операции

## Requirements

### Requirement: Документы движения металла

#### Scenario: Проведение документа

- GIVEN документ в статусе `draft` с заполненными строками
- WHEN нажимается "Post"
- THEN каждая строка валидируется (вес > 0, наличие хранилищ по типу операции, для receipt — partner и rate_datetime)
- AND создаются записи jewelry.metal.move
- AND пересчитываются running_balance по всем затронутым комбинациям (storage × alloy)
- AND документ переходит в `posted`
- AND событие логируется

#### Scenario: Отмена документа

- GIVEN документ в статусе `posted`
- WHEN нажимается Cancel
- THEN move записи переходят в state=cancel
- AND running_balance пересчитывается
- AND документ переходит в `cancel`

#### Scenario: Логика создания move по типу операции

| Тип | Движения |
|-----|----------|
| receipt | +weight в dest_storage |
| transfer | −weight из source_storage, +weight в dest_storage |
| writeoff | −weight из source_storage |
| remelt | −weight из source_storage (input alloy), +output_weight в dest_storage (output alloy) |

---

### Requirement: Типы операций и валидация

- **receipt**: требуется partner, dest_storage, rate_datetime → рассчитывается информационная стоимость
- **transfer**: требуется source_storage ≠ dest_storage
- **writeoff**: требуется source_storage
- **remelt**: требуется source_storage, dest_storage, output_alloy_id, output_weight > 0, loss_weight ≥ 0

---

### Requirement: Автоматические документы из заказов

#### Scenario: Синхронизация документа при приёмке менеджером

- GIVEN менеджер нажимает "Accept Ready Item" или "Sync Metal Documents" на заказе
- THEN создаётся (или пересоздаётся) один metalдокумент на заказ
- AND строки с consume_from_stock=True и alloy_id и weight > 0 → строки writeoff
- AND строки с return_to_storage=True и return_storage_id и alloy_id и weight > 0 → строки receipt
- AND у writeoff строк должен быть source_storage_id — иначе ошибка
- AND у return строк должен быть return_storage_id — иначе ошибка (валидация до создания)
- AND документ проводится автоматически

---

### Requirement: Потери металла при завершении операции

#### Scenario: Создание записи потери

- GIVEN операция завершается (Done)
- AND у материальных строк операции есть consume_from_stock=True, alloy_id заполнен, weight_loss > 0
- THEN создаётся jewelry.metal.loss запись для каждой такой строки
- AND storage = executor_metal_storage_id операции
- AND если executor_metal_storage_id не заполнен — ошибка

#### Scenario: Удаление потерь при откате

- GIVEN операция возвращается в rework или pending, или отменяется
- THEN все связанные jewelry.metal.loss записи удаляются

---

### Requirement: Ведомость остатков

#### Scenario: Построение ведомости

- GIVEN задан период и опциональные фильтры (хранилища, сплавы)
- WHEN нажимается "Build Statement"
- THEN создаются строки с: opening_balance (до date_from), weight_in, weight_out (за период), closing_balance, closing_balance_fine
- AND строки с нулевыми остатками исключаются (если include_zero_lines=False)

#### Scenario: Детализация в движения

- GIVEN строка ведомости
- WHEN нажимается "View Moves"
- THEN открывается список jewelry.metal.move за период для данного хранилища/сплава

#### Scenario: Печать ведомости (PDF)

- GIVEN ведомость построена
- WHEN нажимается "Print Statement"
- THEN формируется PDF-отчёт

---

### Requirement: Заполнение трансфера и списания из остатков

#### Scenario: Fill from Source Storage

- GIVEN документ типа `transfer` в статусе draft, заполнен source_storage_id
- WHEN нажимается "Fill from Source Storage"
- THEN в строки добавляются все сплавы с положительным балансом в source_storage на дату документа
- AND предыдущие строки удаляются

#### Scenario: Обнуление склада на дату

- GIVEN документ типа `writeoff` или `mixed` в статусе draft, заполнен source_storage_id
- WHEN нажимается "Fill from Source Storage"
- THEN по каждому сплаву с положительным остатком на дату документа создаётся строка списания с source_storage
- AND по каждому сплаву с отрицательным остатком — строка поступления на source_storage на модуль остатка, котировка на дату документа
- AND если типы строк расходятся с типом документа, документ становится `mixed`
- AND после проведения все остатки source_storage на дату документа равны нулю

---

## Субдомены

- `rates/` — котировки металла и расчёт цены
- `flow/` — workflow документов металла
- `calculation/` — автоматический расчёт расхода металла из заказов
- `loss/` — потери металла по участкам работы
