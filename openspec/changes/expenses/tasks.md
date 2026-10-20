# Tasks: Expenses — Расходы мастерской

## 1. Скелет модуля

- [x] 1.1 Создать `custom_addons/jewelry_expenses/__manifest__.py` — зависит от `jewelry_repair_base`, `account`; `post_init_hook`
- [x] 1.2 Создать `__init__.py`, `hooks.py`, `models/`, `data/`, `security/`, `views/`, `i18n/`

## 2. Expense Accounts (предопределённые статьи)

- [x] 2.1 `_ensure_expense_accounts()` на модели — идемпотентно создаёт 6 счетов
  EXP100 Rent, EXP200 Tools, EXP300 Consumables, EXP400 Purchases, EXP500 Payroll, EXP900 Other
  (`account_type='expense'`, `reconcile=False`) для каждой компании
- [x] 2.2 `post_init_hook` вызывает `_ensure_expense_accounts` (для существующих БД с готовым планом счетов)
- [x] 2.3 Ленивое создание при открытии Expenses (server action вызывает `_ensure_expense_accounts`) —
  страховка для clean install, где план счетов грузится последним и стирает статические записи

## 3. Модель `jewelry.expense.entry`

- [x] 3.1 Поля: `name` (sequence), `date`, `account_id` (domain expense), `amount`, `currency_id`,
  `payment_journal_id` (cash/bank, default — первая касса), `partner_id`, `notes`, `state`, `move_id`
- [x] 3.2 `create()` — присвоение `name` из `ir.sequence`
- [x] 3.3 `action_post`: проверка amount > 0; `account.move` (`entry`, journal = касса/банк):
  DR expense account / CR default account журнала; пост; `state → posted`
- [x] 3.4 `action_cancel`: сторнирует проводку (`_reverse_moves(cancel=True)`), `state → cancelled` (проведённые проводки нельзя удалять — audit trail Odoo 17)
- [x] 3.6 `action_reset_to_draft`: `button_draft` + правка на месте; повторный `action_post` переиспользует draft-проводку (обновление строк через `(1,id,vals)`, без удаления — audit trail)
- [x] 3.5 Права доступа в `security/ir.model.access.csv` (manager/director/system)

## 4. Views + меню

- [x] 4.1 List view — дата, номер, статья, поставщик, журнал, сумма, статус; фильтры Draft/Posted/This Month; group by
- [x] 4.2 Form view — одноэкранная; Post в draft; Cancel при posted; smart button на move; readonly при posted
- [x] 4.3 `ir.sequence` для номера
- [x] 4.4 Меню Expenses (верхний уровень): Expenses (server action), Vendor Bills (стандарт in_invoice),
  Configuration → Expense Categories (account.account, expense)

## 5. KPI Dashboard — P&L

- [x] 5.1 Transient `jewelry.repair.kpi.expense.line`; поля на дашборде:
  `expense_month_ids`/`expense_prev_ids`, `expense_total_current`/`_prev`, `profit_current`/`_prev`
- [x] 5.2 `_get_expense_data(date_from, date_to)` — read_group `account.move.line` по expense accounts (posted)
- [x] 5.3 Override `action_open_dashboard` — дозаполняет expense-строки и прибыль
- [x] 5.4 Inherit form view — секция Expenses (две таблицы) + Net Profit (красным при минусе)

## 6. Локализация

- [x] 6.1 `i18n/ru.po` — перевод всех строк модуля

## 7. Проверка

- [x] 7.1 Clean install всех модулей + jewelry_expenses: 86 тестов зелёные, install без ошибок
- [x] 7.2 E2E shell: создание/проведение расхода (касса) → проводка DR/CR, остаток кассы −500; отмена возвращает остаток
- [x] 7.3 KPI: expense_total и Net Profit считаются (Payroll 1200 + Consumables 500 → −1700 при revenue 0)
