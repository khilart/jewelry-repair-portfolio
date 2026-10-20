# Metal Accounting / Flow — Workflow металлического учёта

## Purpose

Описание workflow документов металла: жизненный цикл документа, привязка к заказам, идемпотентная синхронизация при повторных вызовах.

Модуль: `jewelry_metal_accounting`

Историческое ТЗ: `METAL_ACCOUNTING_FLOW_SPEC.md`

## Requirements

### Requirement: Жизненный цикл документа

Документ проходит: `draft → posted → cancel → draft` (cancel → draft через action_reset_to_draft).

#### Scenario: Проведение (Post)

- GIVEN документ в `draft` с заполненными строками
- WHEN проводится
- THEN строки валидируются (вес > 0, необходимые хранилища, для receipt — partner и rate_datetime)
- AND создаются move-записи, пересчитываются балансы
- AND документ переходит в `posted`, событие логируется

#### Scenario: Отмена (Cancel)

- GIVEN документ в `posted`
- WHEN отменяется
- THEN move-записи переводятся в cancel, балансы пересчитываются
- AND документ переходит в `cancel`

#### Scenario: Сброс в черновик

- GIVEN документ в `cancel`
- WHEN Reset to Draft
- THEN cancelled moves удаляются
- AND документ переходит в `draft`

---

### Requirement: operation_type на уровне строки

`operation_type` задаётся на каждой строке документа (receipt/transfer/writeoff/remelt). Заголовок документа хранит `operation_type` как значение по умолчанию для новых строк.

---

### Requirement: Идемпотентная синхронизация документа заказа

#### Scenario: Sync при изменении строк заказа

- GIVEN заказ в `ready` с существующим металлодокументом
- WHEN менеджер нажимает "Sync Metal Documents" (или вызывается автоматически при Accept Ready Item)
- THEN если документ posted → cancel → reset_to_draft
- AND строки документа удаляются, создаются заново
- AND документ проводится
- ЕСЛИ строк для движения нет → документ удаляется

#### Scenario: Привязка к заказу

- GIVEN металлодокумент создан из заказа
- THEN repair_order_id связывает документ с заказом
- AND source_repair_order_id вычислен через repair_order_id или source_operation_id.order_id

---

### Requirement: Журнал изменений документа

Все события (create, write, post, cancel, reset_to_draft) логируются в jewelry.metal.document.log с пользователем, временем, описанием.

---

### Requirement: Кнопка "Sync Metal Documents" на заказе

- Видна менеджеру/администратору в статусе `ready`
- При успехе — пересоздаёт документ
- Если есть непокрытые строки (consume_from_stock=True, не в счёт и не на возврат) — предупреждение (не блокирует)
