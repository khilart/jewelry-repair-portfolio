# Client Metal Accounts — Клиентские металл-счета

## Purpose

Лицевые счета клиентов по металлу в единицах чистого металла (fine grams). Клиент может сдавать металл в мастерскую, а при биллинге расходы по заказу списываются с металл-счёта вместо денежной оплаты. Интегрируется с биллингом для расчёта скидки на инвойс.

Модуль: `jewelry_client_metal_accounts`

Исторические ТЗ: `CLIENT_METAL_ACCOUNTS_SPEC.md`, `CLIENT_METAL_OPERATION_PLAN.md`

## Ключевые модели

### jewelry.client.metal.account — Металл-счёт клиента

| Поле | Тип | Описание |
|------|-----|----------|
| partner_id | Many2one (res.partner) | Клиент |
| metal_id | Many2one (jewelry.metal) | Металл |
| company_id | Many2one | Компания |
| active | Boolean | Активен |
| balance_fine | Float | Баланс в fine grams (сумма транзакций) |
| balance_18k | Float | Эквивалент в 18k граммах (balance_fine / 0.750) |
| balance_14k | Float | Эквивалент в 14k граммах (balance_fine / 0.585) |
| balance_9k | Float | Эквивалент в 9k граммах (balance_fine / 0.375) |
| transaction_ids | One2many | Транзакции |

Уникальность: один счёт на (client, metal, company).

### jewelry.client.metal.transaction — Транзакция металл-счёта

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Референс (авто из последовательности) |
| account_id | Many2one | Счёт |
| transaction_type | Selection | deposit_metal / deposit_cash / debit_repair / credit_return / adjustment |
| transaction_date | Datetime | Дата (в часовом поясе пользователя) |
| alloy_id | Many2one | Сплав |
| weight_alloy | Float | Вес в сплаве (г) |
| purity | Float | Чистота сплава |
| weight_fine | Float | Вес в fine grams (± знак) |
| rate_datetime | Datetime | Дата котировки |
| rate_price_per_gram | Monetary | Котировка за грамм fine |
| money_equivalent | Monetary | Денежный эквивалент (для deposit_cash) |
| state | Selection | posted / cancelled |
| receipt_id | Many2one (jewelry.client.metal.receipt) | Источник-квитанция |
| source_model / source_res_id / source_ref | Char/Int/Char | Ссылка на источник |

Правила знака weight_fine:
- deposit_metal, deposit_cash → положительный
- debit_repair, credit_return → отрицательный
- adjustment → знак как введён в строке квитанции (минус в весе сплава уменьшает счёт)

### jewelry.client.metal.receipt — Квитанция металл-счёта

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Референс (авто) |
| operation_type | Selection | deposit_metal / deposit_cash / credit_return / adjustment |
| partner_id | Many2one (res.partner) | Клиент |
| account_id | Many2one (jewelry.client.metal.account) | Счёт клиента |
| operation_date | Datetime | Дата |
| state | Selection | draft / posted / cancelled |
| storage_id | Many2one (jewelry.metal.storage) | Хранилище (для deposit_metal, credit_return) |
| line_ids | One2many | Строки по сплавам |
| metal_document_id | Many2one (jewelry.metal.document) | Созданный металлодокумент (для deposit_metal, credit_return) |
| transaction_ids | One2many | Созданные транзакции |
| notes | Text | Примечания |

### jewelry.client.metal.receipt.line — Строка квитанции

| Поле | Тип | Описание |
|------|-----|----------|
| receipt_id | Many2one | Квитанция |
| alloy_id | Many2one | Сплав |
| weight_alloy | Float | Вес в сплаве (г) |
| purity | Float | Чистота (авто из сплава) |
| weight_fine | Float | Fine grams (авто: вес сплава × чистота для deposit_metal / credit_return / adjustment, денежный эквивалент / котировка для cash) |
| rate_datetime | Datetime | Дата котировки |
| rate_price_per_gram | Monetary | Котировка |
| money_equivalent | Monetary | Денежный эквивалент (для cash) |

### jewelry.repair.billing.line (расширение)

Добавляются поля для управления металлооплатой:

| Поле | Тип | Описание |
|------|-----|----------|
| total_pricing_fine | Float | Fine grams стоимости металла в заказе |
| total_metal_invoice_amount | Monetary | Сумма материальных строк в счёте |
| total_debit_fine_max | Float | Максимально возможный дебет (весь заказ в fine g) |
| client_metal_debit_fine | Float | Дебет с металл-счёта (fine g) — редактируемое |
| metal_amount_reduction | Monetary | Сумма скидки на инвойс |
| effective_amount_total | Monetary | Итог после скидки |

### jewelry.repair.billing.batch (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| client_metal_account_id | Many2one (jewelry.client.metal.account) | Металл-счёт клиента для дебитования |
| client_metal_account_balance | Float | Баланс счёта (fine g, readonly) |
| total_metal_fine_selected | Float | Fine grams по выбранным строкам |
| total_debit_fine_selected | Float | Суммарный дебет по выбранным строкам |

### jewelry.metal.alloy (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| show_in_client_balance | Boolean | Показывать в отображении баланса по сплавам |

### jewelry.repair.ar.summary — Дебиторская задолженность (SQL View, расширение)

Обновляется вид: учитывает effective_amount_total при расчёте pending_invoice_amount.

## Requirements

### Requirement: Металл-счёт клиента

#### Scenario: Баланс в чистом металле

- GIVEN клиент с металл-счётом по золоту
- WHEN просматривается баланс
- THEN баланс отображается в fine grams (сумма всех posted транзакций weight_fine)
- AND также вычисляются эквиваленты в 18k, 14k, 9k граммах (для справки)

---

### Requirement: Пополнение металл-счёта через квитанцию

#### Scenario: Пополнение физическим металлом (deposit_metal)

- GIVEN клиент сдаёт металл мастерской
- WHEN создаётся квитанция типа `deposit_metal`, заполняются строки по сплавам
- AND квитанция подтверждается
- THEN проверяется: строки заполнены, указан storage
- AND создаётся jewelry.metal.document (receipt) в хранилище, проводится
- AND создаются транзакции deposit_metal с положительным weight_fine на металл-счёте

#### Scenario: Пополнение деньгами (deposit_cash)

- GIVEN квитанция типа `deposit_cash` с заполненными money_equivalent и rate_price_per_gram
- WHEN подтверждается
- THEN создаются транзакции deposit_cash (weight_fine = money_equivalent / rate)
- AND металлодокумент НЕ создаётся

#### Scenario: Возврат металла клиенту (credit_return)

- GIVEN квитанция типа `credit_return` с заполненным storage
- WHEN подтверждается
- THEN создаётся jewelry.metal.document (writeoff) из хранилища, проводится
- AND транзакции credit_return с отрицательным weight_fine

#### Scenario: Отмена квитанции

- GIVEN квитанция в статусе posted
- WHEN отменяется
- THEN транзакции переводятся в cancelled
- AND металлодокумент (если есть) отменяется

---

### Requirement: Покрытие заказа металлом при биллинге

#### Scenario: Дебет только металла (Fill Metal)

- GIVEN строка биллинга или батч в режиме draft
- WHEN пользователь нажимает "Fill Metal" на строке (или "Fill All Metal" на батче)
- THEN client_metal_debit_fine = total_pricing_fine строки

#### Scenario: Дебет всей суммы (Fill Full)

- WHEN пользователь нажимает "Fill Full" на строке (или "Fill All Full" на батче)
- THEN client_metal_debit_fine = total_debit_fine_max строки

#### Scenario: Ограничение дебета

- GIVEN client_metal_debit_fine изменяется
- THEN значение зажимается: 0 ≤ debit ≤ total_debit_fine_max

#### Scenario: Скидка на инвойс при подтверждении батча

- GIVEN батч с заполненным client_metal_account_id, строки с client_metal_debit_fine > 0
- WHEN батч подтверждается
- THEN для каждой строки с дебетом создаётся транзакция debit_repair на металл-счёте (отрицательный weight_fine)
- AND при создании инвойса: цена материальных строк уменьшается пропорционально дебету
- AND если debit > metal_cost, разница вычитается из услуг/камней пропорционально
- AND если effective_amount_total ≤ 0 — заказ исключается из инвойса

#### Scenario: Обязательность металл-счёта при дебете

- GIVEN строки с client_metal_debit_fine > 0, но client_metal_account_id не выбран
- WHEN подтверждается батч
- THEN ошибка: выберите металл-счёт клиента

---

### Requirement: Отмена и откат

- При отмене батча: транзакции debit_repair удаляются
- При сбросе в draft: то же самое

---

## UI

- Кнопки "Fill Metal" / "Fill Full" на каждой строке биллинга
- Кнопки "Fill All Metal" / "Fill All Full" на форме батча
- Поля metal_account_id, balance, totals видны на форме батча
- Меню в разделе Payments: Client Metal Accounts, Metal Transactions, Client Metal Receipts
