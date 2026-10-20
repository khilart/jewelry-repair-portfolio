# Tasks: Billing UX Improvements

## 1. Автозаполнение периода в батче

- [ ] 1.1 Добавить `onchange` на `partner_id` в `billing.batch`
- [ ] 1.2 Логика: найти последний `done`-батч для клиента, взять `date_to + 1 day`
- [ ] 1.3 Если батчей нет — `date_from` не заполнять
- [ ] 1.4 Добавить перевод в `i18n/ru.po`

## 2. Дашборд Pending Billing

- [ ] 2.1 Создать computed model или SQL view с агрегацией по клиенту
- [ ] 2.2 Создать `ir.actions.act_window` с list view
- [ ] 2.3 Колонки: клиент, последний биллинг, кол-во заказов, сумма
- [ ] 2.4 Кнопка создания батча из строки дашборда
- [ ] 2.5 Добавить пункт меню в раздел Payments

## 3. Фильтры и группировки в списке заказов

- [ ] 3.1 Добавить `payment_status` computed+stored на `jewelry.repair.order`
   - `unbilled` — delivered, не billing
   - `unpaid` — billing есть, invoice не оплачен
   - `partial` — частично оплачен
   - `paid` — полностью оплачен
- [ ] 3.2 Добавить фильтры по `payment_status` в `search` view
- [ ] 3.3 Добавить Group By billing_date (month) и delivery_date (month)
- [ ] 3.4 Добавить переводы в `i18n/ru.po`
