# Portal — Клиентский портал

## Purpose

Клиентский портал для просмотра статусов заказов ремонта, истории выданных заказов, дебиторской задолженности, камней и сертификатов. Доступ предоставляется через настраиваемые права (`jewelry.portal.access`).

Модуль: `jewelry_repair_portal`

Историческое ТЗ: `PORTAL_SPEC.md`

## Ключевые модели

### jewelry.portal.access — Права доступа портала

| Поле | Тип | Описание |
|------|-----|----------|
| user_id | Many2one (res.users, share=True) | Портальный пользователь |
| partner_id | Many2one (res.partner) | Клиент, чьи заказы видит этот пользователь |
| show_operations | Boolean | Показывать производственный маршрут |
| collapse_new_product_services | Boolean | Сворачивать услуги нового изделия в одну строку |
| show_uninvoiced_gems | Boolean | Показывать камни вне счёта |

Уникальность: один портальный пользователь может иметь доступ к нескольким клиентам; один клиент — к нескольким пользователям.

## Requirements

### Requirement: Доступ к заказам

Портальный пользователь видит только заказы клиентов, к которым ему предоставлен доступ через jewelry.portal.access.

#### Scenario: Список активных заказов

- GIVEN портальный пользователь с настроенным доступом
- WHEN открывает /my/repairs (вкладка active)
- THEN видит заказы в статусах draft/in_progress/ready, отсортированные по deadline_date

#### Scenario: Список заказов "To Pay"

- GIVEN вкладка to_pay
- THEN отображаются выданные заказы с payment_status ∈ unbilled/unpaid/partial
- AND показывается total_outstanding (сумма к оплате)
- AND advance_amount (аванс/переплата по receivable счетам)
- AND net_to_pay = max(0, total_outstanding − advance_amount)

#### Scenario: Список оплаченных заказов

- GIVEN вкладка paid
- THEN отображаются выданные заказы с payment_status = paid

---

### Requirement: Детальная страница заказа

#### Scenario: Просмотр детали заказа

- GIVEN клиент открывает /my/repairs/{id}
- THEN видит: статус, описание, изображение изделия, список услуг, материалы в счёт, сумму
- AND amount_to_pay = order.amount_total (только выставляемые позиции)
- AND amount_full = amount_to_pay + uninvoiced_gems_total (если есть невыставленные камни)
- AND если amount_to_pay ≠ amount_full — показываются оба итога

#### Scenario: Производственный маршрут

- GIVEN show_operations=True в portal_access
- WHEN клиент открывает заказ
- THEN показывается маршрут: зоны сгруппированы по area_id с агрегированным статусом
- AND операции без зоны показываются отдельно
- AND состояние зоны: done (все оп. done), in_progress, accepted, ready, pending

#### Scenario: Камни в заказе

- GIVEN show_uninvoiced_gems=True → показываются все камни
- GIVEN show_uninvoiced_gems=False → только include_in_invoice=True
- THEN таблица: тип камня, сертификат (ссылка), кол-во, вес (ct), сумма
- AND по клику на сертификат открывается Bootstrap 5 modal с полными данными

#### Scenario: Сворачивание услуг нового изделия

- GIVEN collapse_new_product_services=True, заказ new_product_manufacturing=True
- THEN услуги заказа скрываются / показываются одной сводной строкой

---

### Requirement: Счётчик на главной странице портала

- GIVEN портальный пользователь открывает My Account
- THEN отображается счётчик: "X repair orders" (не отменённые заказы доступных клиентов)

---

### Requirement: Безопасность

- ORM: при любом поиске заказов портальным пользователем автоматически добавляется фильтр по partner_id из его portal_access записей
- Прямой запрос к /my/repairs/{id} для чужого клиента → 404 (MissingError)
