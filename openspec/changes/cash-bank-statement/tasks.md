# Tasks: Cash & Bank Statement

## 1. Строки проводок (`jewelry_repair_billing`)

- [x] 1.1 `account.move.line.counterpart_account_id` — другая строка проводки с наибольшей суммой
- [x] 1.2 `account.move.line.running_balance` — остаток счёта после строки, вся история, `(date, id)`
- [x] 1.3 Список движений (tree `account.move.line`): дата, проводка, партнёр, описание,
      корреспондент, In, Out, Balance; свежие сверху
- [x] 1.4 Кнопка Movements в списке `Cash & Bank`

## 2. Мастер ведомости

- [x] 2.1 `jewelry.cash.bank.statement`: пресет, даты, проверка дат, валюта компании
- [x] 2.2 `jewelry.cash.bank.statement.account`: Opening / In / Out / Closing + Movements
- [x] 2.3 `jewelry.cash.bank.statement.line`: корреспондент, подпись, In / Out, число проводок,
      строки кассы (m2m) + Movements
- [x] 2.4 Открытие из меню сразу с построенной ведомостью за текущий месяц
- [x] 2.5 Права: manager, director, system; пункт меню в `Payments`

## 3. Печать

- [x] 3.1 QWeb PDF в `jewelry_layout_minimalist`

## 4. Завершение

- [x] 4.1 Тесты: остатки/обороты, отменённая проводка, корреспондент и подписи, сторно,
      running_balance с отсечкой по дате
- [x] 4.2 `ru.po`
- [x] 4.3 Проверка на `testWork`: суммы сходятся с `Cash & Bank`, рендер PDF
- [ ] 4.4 Проверка в UI пользователем, затем архив спеки и влитие дельты в
      `openspec/specs/repair/billing/spec.md`
