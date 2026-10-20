# Repair / Delivery — Выдача заказов

## Purpose

Управляет процессом физической выдачи готовых изделий клиенту. Объединяет несколько заказов одного клиента в один документ выдачи. Предоставляет печатные формы с разбивкой по услугам и материалам.

Модуль: `jewelry_repair_delivery`

## Ключевые модели

### jewelry.repair.delivery — Документ выдачи

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Номер (авто из последовательности) |
| partner_id | Many2one (res.partner) | Клиент |
| delivery_date | Date | Дата выдачи |
| state | Selection | draft / done / cancel |
| order_ids | Many2many (jewelry.repair.order) | Выбранные заказы для выдачи |
| line_ids | One2many | Строки кандидатов (все готовые заказы клиента) |
| confirmed_line_ids | Many2many | Подтверждённые строки (только из order_ids) |
| notes | Text | Примечания |
| order_count | Integer | Количество заказов |
| selected_order_count | Integer | Количество выбранных заказов |
| selected_amount_total | Monetary | Сумма выбранных заказов |
| available_order_count | Integer | Количество доступных кандидатов |
| billing_status | Selection | not_billed / billed (computed, из billing_ext) |

### jewelry.repair.delivery.line — Строка кандидата

| Поле | Тип | Описание |
|------|-----|----------|
| delivery_id | Many2one | Документ выдачи |
| selected | Boolean | Включить в выдачу |
| order_id | Many2one (jewelry.repair.order) | Заказ |
| order_name | Char | Номер заказа |
| order_item_image | Image | Фото изделия |
| order_amount_total | Monetary | Сумма заказа |
| order_item_type_id | Many2one | Тип изделия |
| order_deadline_date | Datetime | Дедлайн |
| order_description | Text | Описание |
| order_state | Selection | Статус заказа |

### jewelry.repair.order (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| delivery_id | Many2one (jewelry.repair.delivery) | Документ выдачи (readonly) |
| delivery_date | Date | Дата выдачи (readonly) |

## Requirements

### Requirement: Создание документа выдачи

При выборе клиента документ автоматически заполняется готовыми к выдаче заказами.

#### Scenario: Автоматическая загрузка кандидатов

- GIVEN документ выдачи создан, выбран клиент
- WHEN клиент выбирается или документ создаётся
- THEN в строки-кандидаты загружаются все заказы клиента в статусе `ready`, принятые менеджером (`ready_accepted_by_manager=True`), ещё не привязанные к другому документу выдачи
- AND строки сортируются по deadline_date, затем id
- AND все флаги selected=False по умолчанию

#### Scenario: Выбор заказов для выдачи

- GIVEN документ в статусе draft
- WHEN пользователь ставит флаг "Deliver" на строке
- THEN order_ids обновляется — синхронизируется из выбранных строк
- AND доступны кнопки "Select All" и "Clear Selected"

---

### Requirement: Подтверждение выдачи

#### Scenario: Подтверждение документа выдачи

- GIVEN документ с выбранными заказами (order_ids не пустой)
- WHEN нажимается "Confirm"
- THEN проверяется: каждый заказ принадлежит тому же клиенту, находится в статусе `ready`, принят менеджером, не привязан к другому документу — иначе ошибка
- AND заказы переходят в статус `delivered`
- AND у каждого заказа заполняются: delivery_id, delivery_date, current_holder_role=customer, current_location_type=delivered, last_move_at=now
- AND документ переходит в `done`

#### Scenario: Отмена документа выдачи

- GIVEN документ в статусе `done`
- WHEN нажимается "Cancel"
- THEN проверяется, что ни один заказ не имеет billing_batch_id — иначе ошибка
- AND заказы возвращаются в статус `ready`, delivery_id=False, delivery_date=False, current_location_type=ready_for_delivery
- AND документ переходит в `cancel`

---

### Requirement: Печатные формы

- Кнопка "Print" — стандартная детализированная форма выдачи (PDF)
- Кнопка "Print EN" — та же форма на английском языке
- Кнопка "Print Grouped" — сгруппированные услуги; новые изделия объединяются в одну строку "Manufacture of New Item"

---

### Requirement: Статус биллинга

Документ выдачи показывает `billing_status`: billed (все заказы попали в billing batch) / not_billed. Статус вычислен и хранится.

---

### Requirement: Защита от изменений

#### Scenario: Выданный заказ нельзя изменить

- GIVEN заказ в статусе `delivered`
- WHEN пользователь (не администратор) пытается изменить поля заказа (кроме delivery_id, billing_batch_id, state, current_holder_*, last_move_at, ready_accepted_*)
- THEN ошибка: выданные заказы только для чтения

#### Scenario: Директор — только чтение

- GIVEN пользователь с ролью Директор
- WHEN он пытается изменить документ выдачи или заказ
- THEN ошибка: директоры имеют доступ только на чтение

---

## Физическое разделение

```
delivery (факт физической выдачи)  ≠  billing (отбор выданных заказов в пакет)  ≠  invoice (стандартный счёт Odoo)
```

В счёт попадают только выданные (`delivered`) заказы, без повторного биллинга.

## Ссылки

Исторических ТЗ в корне проекта нет.
