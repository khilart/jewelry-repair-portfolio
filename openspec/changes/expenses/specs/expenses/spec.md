# Delta: Expenses — Расходы мастерской

## ADDED

---

### Requirement: Предопределённые статьи расходов (expense accounts)

Модуль `jewelry_expenses` создаёт преднастроенные expense accounts
(`account_type='expense'`) — они же категории в документе расхода:

| Код    | Название       | Назначение                               |
|--------|----------------|------------------------------------------|
| EXP100 | Rent           | Аренда помещения                         |
| EXP200 | Tools          | Инструменты и оборудование               |
| EXP300 | Consumables    | Расходные материалы                      |
| EXP400 | Purchases      | Закупки (материалы не для заказов)       |
| EXP500 | Payroll        | Оплата труда                             |
| EXP900 | Other Expenses | Прочие расходы                           |

Счета создаются программно (`_ensure_expense_accounts`): через `post_init_hook`
и лениво при открытии экрана Expenses. Статический XML не используется —
`account.account` из XML удаляются при загрузке плана счетов.

#### Scenario: Статьи доступны при работе с расходами

- GIVEN модуль `jewelry_expenses` установлен и план счетов загружен
- WHEN пользователь открывает меню Expenses
- THEN в системе присутствуют 6 expense accounts с кодами EXP*
- AND они доступны в поле «Статья расхода» документа быстрого расхода

---

### Requirement: Документ быстрого расхода `jewelry.expense.entry`

Поля:
- `name` — Char, номер из sequence (`EXP%(year)s-####`), readonly
- `date` — Date (required, default today)
- `account_id` — Many2one `account.account` (required, domain `account_type='expense'`)
- `amount` — Monetary (required, валюта компании)
- `payment_journal_id` — Many2one `account.journal` (required, domain `type in (cash, bank)`,
  default — первая касса компании)
- `partner_id` — Many2one `res.partner` (опц., поставщик/получатель; для зарплат — мастер)
- `notes` — Char (опц.)
- `state` — Selection `draft` / `posted`
- `move_id` — Many2one `account.move` (readonly)

#### Scenario: Проведение расхода из кассы

- GIVEN открыт документ расхода в статусе Draft с суммой 500, статьёй EXP300, журналом Cash
- WHEN пользователь нажимает **Post**
- THEN создаётся и постится `account.move` (`move_type='entry'`, journal = Cash):
  - Строка 1: `account_id` = EXP300, `debit` = 500
  - Строка 2: `account_id` = default account журнала Cash, `credit` = 500
- AND `state` = posted, `move_id` заполнен
- AND остаток кассы уменьшается на 500

#### Scenario: Проведение расхода из банка

- GIVEN документ расхода с журналом Bank
- WHEN пользователь нажимает Post
- THEN проводка кредитует счёт банковского журнала; остаток банка уменьшается

#### Scenario: Зарплата как статья расхода

- GIVEN документ расхода со статьёй EXP500 Payroll и поставщиком = мастер
- WHEN пользователь нажимает Post
- THEN сумма относится на счёт Payroll; отдельный документ зарплаты не используется

#### Scenario: Нулевая сумма запрещена

- GIVEN документ расхода с amount = 0
- WHEN пользователь нажимает Post
- THEN ошибка: «The expense amount must be greater than zero.»

#### Scenario: Исправление расхода (Reset to Draft)

- GIVEN расход в статусе Posted с неверной суммой
- WHEN пользователь нажимает **Reset to Draft**, исправляет сумму и снова **Post**
- THEN проводка возвращается в draft (`button_draft`), затем **переиспользуется** (строки
  обновляются через `(1, id, vals)`, новая проводка не создаётся); остаток кассы соответствует
  новой сумме; сторнирующих записей нет
- AND если период закрыт (lock date / hash) — Odoo не даёт вернуть в черновик (штатная ошибка)

#### Scenario: Отмена расхода

- GIVEN расход в статусе Posted
- WHEN пользователь нажимает **Cancel**
- THEN создаётся и постится встречная (сторнирующая) проводка `_reverse_moves(cancel=True)`;
  остаток кассы/банка восстанавливается; оригинальная проводка сохраняется (audit trail);
  `state` = `cancelled`, документ становится read-only

---

### Requirement: Vendor Bills (стандартный Odoo)

Счета поставщиков с отсрочкой ведутся стандартными Vendor Bills (`account.move`, `in_invoice`)
через пункт меню. Кастомизации нет.

#### Scenario: Создание расхода через Vendor Bill

- GIVEN пользователь открывает Expenses → Vendor Bills
- WHEN создаёт bill: поставщик, строка с expense account (напр. EXP200 Tools), сумма; Confirm
- THEN создаётся posted vendor bill; сумма попадает на expense account
- AND Register Payment из кассы/банка уменьшает остаток

---

### Requirement: Меню

#### Scenario: Раздел Expenses в главном меню

- GIVEN пользователь с ролью Manager или Director
- THEN в главном меню присутствует пункт **Expenses** (после Payments), а в нём:
  - **Expenses** → список `jewelry.expense.entry` (server action гарантирует статьи)
  - **Vendor Bills** → стандартный список `account.move` (in_invoice)
  - **Configuration → Expense Categories** → список EXP* счетов плана счетов

---

### Requirement: P&L в KPI Dashboard

Расширение `jewelry.repair.kpi.dashboard` и form view через `_inherit` в `jewelry_expenses`.

Источник данных за период (текущий / прошлый месяц): `account.move.line` где
`account_id.account_type='expense'`, `parent_state='posted'`, `date` в периоде.
Один запрос покрывает и быстрые расходы (`entry`), и vendor bills (`in_invoice`),
агрегируется по `account_id` → строки секции Expenses.

#### Scenario: Секция Expenses в дашборде

- GIVEN открыт KPI Dashboard
- THEN отображается секция **Expenses**: строки «название статьи — сумма» за текущий и прошлый месяц
- AND строки с нулём за период не показываются

#### Scenario: Net Profit

- GIVEN секция Expenses отображается
- THEN строка **Net Profit** = Revenue − Total Expenses (для текущего и прошлого месяца)
- AND отрицательный Net Profit выделяется красным

## REMOVED

### Requirement: Документ зарплатной выплаты `jewelry.payroll.entry`

**Reason:** Заменён единым документом быстрого расхода — зарплата ведётся как статья EXP500 Payroll.

### Requirement: Поле monthly_salary на исполнителе

**Reason:** Не нужно без отдельного документа зарплаты.
