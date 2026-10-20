# Repair / Billing — Биллинг

## Purpose

Пакетный биллинг выданных заказов клиента за период. Объединяет несколько выданных заказов в пакет, создаёт счёт Odoo (`account.move`). Отслеживает платёжный статус заказа.

Модуль: `jewelry_repair_billing`

## Ключевые модели

### jewelry.repair.billing.batch — Биллинг-батч

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Номер (авто из последовательности) |
| partner_id | Many2one (res.partner) | Клиент |
| date_from | Date | Начало периода (необязательно) |
| date_to | Date | Конец периода (необязательно) |
| state | Selection | draft / done / cancel |
| order_ids | Many2many (jewelry.repair.order) | Выбранные заказы |
| line_ids | One2many | Строки кандидатов |
| order_count | Integer | Количество заказов |
| amount_total | Float | Итог (из строк услуг + материалов в счёт + камней в счёт) |
| invoice_id | Many2one (account.move) | Связанный инвойс |
| invoice_payment_state | Selection | Статус оплаты инвойса |
| invoice_reference | Char | Номер инвойса |
| notes | Text | Примечания |
| last_billing_date_to | Date | Дата окончания последнего подтверждённого батча для клиента |

### jewelry.repair.billing.line — Строка биллинга

| Поле | Тип | Описание |
|------|-----|----------|
| batch_id | Many2one | Батч |
| selected | Boolean | Включить в биллинг |
| order_id | Many2one (jewelry.repair.order) | Заказ |
| order_name | Char | Номер заказа |
| order_item_type_id | Many2one | Тип изделия |
| order_delivery_date | Date | Дата выдачи |
| order_amount_total | Monetary | Сумма заказа |

### jewelry.repair.order (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| billing_batch_id | Many2one (jewelry.repair.billing.batch) | Биллинг-батч (readonly) |
| billing_date | Date | Дата биллинга (readonly) |
| payment_status | Selection | unbilled / unpaid / partial / paid (вычислен, не хранится) |

### jewelry.repair.ar.summary — Дебиторская задолженность (SQL View)

Агрегированный вид по клиентам: unbilled_amount, pending_invoice_amount, invoiced_unpaid_amount, advance_amount, total_outstanding.

## Requirements

### Requirement: Формирование пакета биллинга

#### Scenario: Загрузка кандидатов

- GIVEN биллинг-батч создан, выбран клиент
- WHEN клиент выбирается или батч создаётся
- THEN в строки-кандидаты загружаются все заказы клиента со статусом `delivered` и billing_batch_id=False
- AND строки сортируются по delivery_date, затем id
- AND все флаги selected=False по умолчанию

#### Scenario: Выбор заказов

- GIVEN батч в статусе draft
- WHEN пользователь ставит флаг "Include" на строке
- THEN order_ids синхронизируется из выбранных строк

#### Scenario: Кнопки выбора

- GIVEN список строк биллинга в статусе draft
- "Select All" — выбирает все строки
- "Select by Period" (требует date_from/date_to) — выбирает строки, где order_delivery_date ∈ [date_from, date_to]
- "Clear" — снимает все выборки

#### Scenario: Автозаполнение периода при выборе клиента

- GIVEN форма батча без дат
- WHEN пользователь выбирает клиента
- THEN date_from = день после date_to последнего подтверждённого батча клиента (или дата первого заказа)
- AND date_to = сегодня

---

### Requirement: Подтверждение биллинга

#### Scenario: Подтверждение батча

- GIVEN батч с выбранными заказами
- WHEN пользователь подтверждает батч
- THEN проверяется: заказы принадлежат клиенту, статус delivered, не попали в другой батч — иначе ошибка
- AND у заказов заполняется billing_batch_id и billing_date
- AND батч переходит в `done`
- AND вызывается `_post_billing_client_metal_transactions()` (хук для расширений)

#### Scenario: Создание инвойса

- GIVEN батч в статусе `done`, инвойс ещё не создан
- WHEN нажимается "Create Invoice"
- THEN создаётся `account.move` (out_invoice) с одной строкой на каждую услугу и материал (include_in_invoice=True) каждого заказа
- AND строки инвойса: product_id, name = "номер_заказа — описание_строки", quantity, price_unit, account_id
- AND у всех продуктов должен быть настроен income account — иначе ошибка
- AND invoice_id батча заполняется
- AND форма инвойса открывается

#### Scenario: Платёжный статус заказа

- GIVEN заказ, привязанный к батчу с инвойсом
- WHEN инвойс оплачен/частично оплачен
- THEN payment_status заказа = paid/partial
- AND заказ без батча → payment_status = unbilled
- AND батч без инвойса → payment_status = unpaid

---

### Requirement: Отмена биллинга

#### Scenario: Отмена батча

- GIVEN батч в статусе done, инвойс (если есть) уже отменён
- WHEN нажимается Cancel
- THEN у заказов очищается billing_batch_id и billing_date
- AND отменяются транзакции металл-счёта (хук)
- AND батч переходит в cancel
- AND если инвойс не отменён — ошибка

#### Scenario: Сброс в черновик

- GIVEN батч в статусе cancel
- WHEN Reset to Draft
- THEN строки-кандидаты перезагружаются
- AND батч переходит в draft

---

### Requirement: Защита от изменений

#### Scenario: Выставленный в счёт заказ нельзя изменить

- GIVEN заказ с заполненным billing_batch_id
- WHEN пользователь (не администратор) пытается изменить поля заказа (кроме delivery_id, billing_batch_id, state, billing_date)
- THEN ошибка: выставленные в счёт заказы только для чтения

#### Scenario: Директор — только чтение

- GIVEN пользователь с ролью Директор
- WHEN он пытается изменить батч или заказ
- THEN ошибка: директоры имеют доступ только на чтение

---

### Requirement: Расширяемые хуки

Биллинг предоставляет overridable методы для дочерних модулей:
- `_get_material_line_invoice_price_unit(line)` — цена строки материала в инвойсе
- `_get_service_line_invoice_price_unit(line)` — цена строки услуги
- `_get_gem_line_invoice_price_unit(line)` — цена строки камня
- `_post_billing_client_metal_transactions()` — транзакции металл-счёта при подтверждении
- `_should_skip_invoice_for_order(order)` — пропустить заказ при создании инвойса

---

## Критичные разделения

```
delivery (факт выдачи)  ≠  billing (отбор в пакет)  ≠  invoice (счёт Odoo)
```

`date_from` / `date_to` — не обязательны и не фильтруют кандидатов при загрузке; используются только кнопкой "Select by Period".
