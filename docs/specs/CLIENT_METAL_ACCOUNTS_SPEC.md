# ТЗ: контур клиентских металл-счетов

## 1. Назначение

Реализовать отдельный контур учёта металла, принадлежащего клиентам мастерской.

Контур работает по банковской модели:
- у каждого клиента есть металл-счёт — обязательство мастерской перед ним
- физический металл мастерской хранится в общем котле (модуль `jewelry_metal_accounting`)
- мастерская может использовать клиентский металл для своих нужд
- разница между физическим остатком и суммой обязательств = собственная позиция мастерской

Контур отвечает на вопросы:
- сколько чистого металла принадлежит каждому клиенту
- каков остаток на металл-счёте клиента в любом целевом сплаве
- сколько мастерская потребила клиентского металла и каков её долг
- какая часть ремонта оплачена металлом, какая деньгами

## 2. Архитектурное решение

Реализуется отдельным модулем Odoo:

```
jewelry_client_metal_accounts
```

Зависимости:
- `jewelry_repair_base`
- `jewelry_metal_accounting`

Принцип разделения:

| Модуль | Что хранит | Единица |
|---|---|---|
| `jewelry_metal_accounting` | Физический металл в хранилищах | граммы сплава |
| `jewelry_client_metal_accounts` | Обязательства перед клиентами | граммы чистого металла (fine) |

Два регистра **независимы**. Связь только через `source_ref` и управленческий отчёт позиции.

## 3. Единица измерения счёта

Металл-счёт клиента ведётся в **граммах чистого металла (fine weight)**.

Причина: клиент может сдать Gold585, а получить изделие в Gold750. Нормализация через пробу позволяет вести единый баланс независимо от сплава.

Формула:
```
fine_weight = weight_alloy × purity
```

Примеры:
- принято 100г Gold585 → +58.5g fine gold
- израсходовано 8г Gold750 → −6.0g fine gold
- остаток 52.5g fine gold

### 3.1. Информационное отображение в других сплавах

Баланс в fine grams хранится как основное значение.

Дополнительно в UI и отчётах отображается пересчёт в распространённые сплавы:

```
Баланс клиента Иванова (Gold):
  Чистый металл:   52.50g
  ≈ Gold 585:      89.74g
  ≈ Gold 750:      70.00g
  ≈ Gold 999:      52.55g
```

Набор сплавов для пересчёта берётся из справочника сплавов (`jewelry.metal.alloy`) по флагу `show_in_client_balance = True`.

## 4. Модели

### 4.1. ClientMetalAccount (`jewelry.client.metal.account`)

Металл-счёт клиента по каждому металлу.

Поля:
- `partner_id` (Many2one → res.partner, required) — клиент
- `metal_id` (Many2one → jewelry.metal, required) — металл (Gold, Silver, Platinum)
- `company_id` (Many2one → res.company, required)
- `balance_fine` (Float, computed, stored, digits 16,4) — остаток в граммах чистого металла
- `currency_id` (Many2one → res.currency, related) — валюта для денежного эквивалента
- `transaction_ids` (One2many → jewelry.client.metal.transaction)
- `active` (Boolean, default=True)

Ограничения:
- уникальность `(partner_id, metal_id, company_id)`

Вычисляемые поля для отображения:
- `balance_display_ids` (One2many → jewelry.client.metal.balance.display) — строки пересчёта в сплавы

### 4.2. ClientMetalTransaction (`jewelry.client.metal.transaction`)

Проводки по металл-счёту клиента.

Поля:

| Поле | Тип | Описание |
|---|---|---|
| `account_id` | Many2one → account | металл-счёт, обязательное |
| `partner_id` | Many2one, related | клиент (для поиска) |
| `metal_id` | Many2one, related | металл (для поиска) |
| `transaction_type` | Selection | тип проводки |
| `transaction_date` | Datetime, required | дата и время |
| `alloy_id` | Many2one → jewelry.metal.alloy | сплав на момент операции |
| `weight_alloy` | Float, digits 16,3 | граммы сплава (аудит) |
| `purity` | Float | проба на момент операции (аудит) |
| `weight_fine` | Float, digits 16,4 | граммы чистого металла (единица счёта) |
| `rate_datetime` | Datetime | дата котировки |
| `rate_price_per_gram` | Monetary | котировка чистого металла |
| `money_equivalent` | Monetary | справочная сумма |
| `state` | Selection: posted / cancelled | статус |
| `notes` | Text | примечание |
| `source_model` | Char | модель источника |
| `source_res_id` | Integer | id источника |
| `source_ref` | Char | отображаемая ссылка |
| `company_id` | Many2one, related | компания |
| `currency_id` | Many2one, related | валюта |

Типы проводок (`transaction_type`):

| Код | Название | Знак | Источник |
|---|---|---|---|
| `deposit_metal` | Приём металла от клиента | + | metal.document (receipt) |
| `deposit_cash` | Пополнение через деньги | + | account.move или вручную |
| `debit_repair` | Списание на ремонт | − | repair.order (при биллинге) |
| `credit_return` | Возврат металла клиенту | − | вручную или metal.document |
| `adjustment` | Ручная корректировка | ± | вручную |

Правила:
- `weight_fine` при создании вычисляется как `weight_alloy × purity`
- знак `weight_fine` определяется типом: `deposit_*` и `adjustment(+)` — плюс, `debit_*` и `credit_return` и `adjustment(−)` — минус
- `balance_fine` в аккаунте = `Σ weight_fine` по всем posted-транзакциям

### 4.3. ClientMetalBalanceDisplay (Transient или computed)

Строки информационного пересчёта баланса в сплавы. Не хранятся в БД — вычисляются на лету при открытии формы счёта.

Поля:
- `alloy_id`
- `purity`
- `weight_in_alloy` = `account.balance_fine / purity`

## 5. Расширение существующих моделей

### 5.1. jewelry.repair.material.line

Добавляются поля для смешанной оплаты.

**Единственное вводимое поле:**

| Поле | Тип | Описание |
|---|---|---|
| `client_metal_weight` | Float, digits 16,3 | сколько граммов физики берётся с металл-счёта (0 ≤ x ≤ weight) |
| `client_metal_account_id` | Many2one → client.metal.account | автозаполнение из заказа |

**Вычисляемые поля (computed):**

| Поле | Формула | Описание |
|---|---|---|
| `split_ratio` | `client_metal_weight / weight` | доля клиентского металла (0.0–1.0) |
| `client_pricing_weight` | `(weight + weight_loss) × split_ratio` | база для списания с металл-счёта (с долей потерь) |
| `client_fine_debit` | `client_pricing_weight × alloy.purity` | fine grams для транзакции по счёту |
| `invoice_pricing_weight` | `(weight + weight_loss) × (1 − split_ratio)` | база для денежного инвойса (с долей потерь) |

**Почему потери распределяются пропорционально:**

Потери при изготовлении (`weight_loss`) — это цена работы с металлом. Клиент несёт расходы по своей доле потерь так же, как и по своей доле физического веса. Нельзя взять физику с металл-счёта, а потери переложить на деньги.

**Пример:**
```
weight = 4g, weight_loss = 1g, pricing_weight = 5g
client_metal_weight = 2g

split_ratio            = 2/4 = 0.5
client_pricing_weight  = 5g × 0.5 = 2.5g  → списать с металл-счёта
invoice_pricing_weight = 5g × 0.5 = 2.5g  → в денежный инвойс

Физический склад: writeoff 4g (без потерь, как сейчас)
Металл-счёт:      debit 2.5g × purity fine grams
Инвойс:           2.5g × alloy_price_per_gram
```

**Правила:**
- `client_metal_weight` не может превышать `weight`
- `client_metal_weight` > 0 требует заполненного `client_metal_account_id`
- `client_metal_account_id` по умолчанию подставляется из `order_id.partner_id` (если у клиента есть счёт по нужному металлу)
- если `include_in_invoice = False`, то `invoice_pricing_weight` не попадает в инвойс независимо от разбивки
- если `client_metal_weight = 0` — поведение как сейчас, новые поля не задействованы
- если `client_metal_weight = weight` — вся строка закрывается металлом, в инвойс ничего не идёт по этой строке

### 5.2. jewelry.repair.order

Добавляется вычисляемое поле:
- `client_metal_account_ids` (Many2many, computed) — металл-счета клиента этого заказа

### 5.3. jewelry.metal.alloy

Добавляется флаг:
- `show_in_client_balance` (Boolean, default=False) — показывать этот сплав в информационном пересчёте баланса

## 6. Бизнес-сценарии

### 6.1. Клиент принёс физический металл

1. Создаётся `jewelry.metal.document` (тип `receipt`) — физический приход в котёл
2. В форме документа или отдельно создаётся `client.metal.transaction` (тип `deposit_metal`)
   - `alloy_id`, `weight_alloy` — из документа
   - `weight_fine` = `weight_alloy × purity` — вычисляется автоматически
   - `source_ref` — ссылка на металл-документ
3. Баланс счёта клиента увеличивается

Связь между документами информационная (source_ref), не принудительная.

### 6.2. Клиент пополнил счёт деньгами

1. Создаётся `client.metal.transaction` (тип `deposit_cash`) вручную или из invoice
2. Указываются: металл, сумма, котировка на дату
3. Система рассчитывает `weight_fine = money_amount / rate_price_per_gram`
4. Физический котёл не меняется — мастерская принимает на себя обязательство

### 6.3. Ремонт завершён, оплата смешанная

На строке материала:
1. Пользователь указывает `client_metal_weight` — сколько граммов физики берётся со счёта клиента
2. Система вычисляет `split_ratio`, `client_pricing_weight`, `invoice_pricing_weight` автоматически
3. Физический склад: writeoff на `weight` (потери не попадают в регистр физики — как сейчас)
4. При биллинге (проводка `billing.batch`):
   - Денежная часть: в `account.move` попадает `invoice_pricing_weight × alloy_price_per_gram`
   - Металлическая часть: создаётся `client.metal.transaction` (тип `debit_repair`)
     - `weight_alloy` = `client_pricing_weight` (физика + пропорциональные потери)
     - `weight_fine` = `client_pricing_weight × alloy.purity`
     - `source_ref` = repair order

**Пример с цифрами:**
```
Строка: Gold750, weight=4g, weight_loss=1g, client_metal_weight=2g

split_ratio            = 0.5
client_pricing_weight  = 2.5g
invoice_pricing_weight = 2.5g

→ Физика: writeoff 4g со склада
→ Металл-счёт: debit 2.5g × 0.750 = 1.875g fine gold
→ Инвойс: 2.5g × price_per_gram_alloy = X ₽
```

### 6.4. Клиент сдал Gold585, кольцо в Gold750

Баланс ведётся в fine grams — конвертация сплавов прозрачна:

```
Пополнение: 100г Gold585 → +58.5g fine gold
Кольцо:     8г Gold750   → −6.0g fine gold (8 × 0.750)
Остаток:    52.5g fine gold
  ≈ 89.7г Gold585 (если вернуть тем же)
  ≈ 70.0г Gold750 (если вернуть другим)
```

Никаких явных транзакций конвертации не требуется.

### 6.5. Возврат металла клиенту

1. Создаётся `jewelry.metal.document` (тип `transfer` или `writeoff`) — физический расход из котла
2. Создаётся `client.metal.transaction` (тип `credit_return`)
   - Указываются сплав и вес, который отдаётся физически
   - Списание со счёта = `weight_alloy × purity` в fine grams
3. Баланс счёта клиента уменьшается

### 6.6. Мастерская использует клиентский металл

Физический котёл уменьшается (writeoff/transfer), клиентские счета не меняются:

```
Позиция мастерской:
  Физически: 400g fine gold
  Обязательства клиентам: 450g fine gold
  Собственная позиция: −50g  ← мастерская в долгу
```

Отрицательная позиция не блокируется, только отображается в управленческом отчёте.

## 7. Интеграция с биллингом

При проводке `billing.batch`:

```
Для каждого repair.order в пакете:
  Для каждой material.line:

    if client_metal_weight > 0:
      → создать client.metal.transaction (debit_repair)
          weight_alloy   = client_pricing_weight
          weight_fine    = client_pricing_weight × alloy.purity
          alloy_id       = line.alloy_id
          source_ref     = repair order ref

    if invoice_pricing_weight > 0 and include_in_invoice:
      → включить в account.move строку с суммой:
          invoice_pricing_weight × alloy_price_per_gram
        (вместо текущего weight × alloy_price_per_gram)
```

**Изменение в существующем биллинге:** вместо `weight + weight_loss` как базы для инвойса используется `invoice_pricing_weight`. Если `client_metal_weight = 0`, то `invoice_pricing_weight = weight + weight_loss` — поведение идентично текущему.

Ограничение первой версии: транзакции создаются при проводке биллинг-пакета, не раньше.

## 8. Отчётность

### 8.1. Выписка по металл-счёту клиента

Аналог банковской выписки:

| Дата | Тип | Сплав | Граммы сплава | Граммы чистого | Остаток fine |
|---|---|---|---|---|---|
| 01.04 | Приём | Gold585 | +100g | +58.50g | 58.50g |
| 15.04 | Списание (ремонт #123) | Gold750 | −8g | −6.00g | 52.50g |
| 20.04 | Пополнение (деньги) | Gold | — | +30.00g | 82.50g |

Фильтры: по клиенту, металлу, периоду.

### 8.2. Управленческий отчёт: позиция по металлу

| Металл | Физически (котёл) | Обязательства | Собственная позиция |
|---|---|---|---|
| Gold | 520.0g fine | 450.0g fine | +70.0g ✓ |
| Silver | 1200.0g fine | 1340.0g fine | −140.0g ⚠ |

Отрицательная позиция — индикатор того, что мастерская использует клиентский металл.

### 8.3. Сводка по клиенту

| Клиент | Gold fine | Silver fine | Денежный эквивалент |
|---|---|---|---|
| Иванов | 82.5g | 0g | 823 000₽ |
| Петров | 0g | 450g | 67 500₽ |

## 9. Интерфейс

### 9.1. Форма металл-счёта клиента

Шапка:
- Клиент, металл, компания
- Остаток: **52.50g fine gold**
- Информационный блок пересчёта в сплавы (только чтение):
  ```
  ≈ 89.7г Gold 585
  ≈ 70.0г Gold 750
  ≈ 52.6г Gold 999
  ```

Вкладки:
- Транзакции (список проводок с фильтром по периоду)
- Аналитика

### 9.2. Расположение в меню

```
Payments (существующий раздел)
  ├── Billing Batches
  ├── Invoices
  └── Client Metal Accounts    ← новый пункт
        ├── Accounts
        └── Transactions
```

### 9.3. Строки материалов в форме заказа

В колонках материальных строк добавляется:
- `Client Metal (g)` — редактируемое поле `client_metal_weight` (граммы физики с металл-счёта)
- `Client Pricing (g)` — вычисляемое только чтение: `client_pricing_weight` (с долей потерь)
- `Invoice Pricing (g)` — вычисляемое только чтение: `invoice_pricing_weight` (с долей потерь)

Колонки `Client Pricing` и `Invoice Pricing` скрыты по умолчанию, открываются кнопкой опциональных колонок.

Если у клиента нет металл-счёта по нужному металлу, поле `client_metal_weight` заблокировано с подсказкой.

## 10. Ограничения первой версии

Не входит в первую версию:
- автоматическая синхронизация с физическим металл-документом при пополнении
- частичный возврат металла при незавершённом заказе
- конвертация между металлами (Gold ↔ Silver)
- процентные начисления или переоценка остатков
- ~~права доступа к металл-счёту клиента для самого клиента (портал)~~ — реализовано 2026-08-31 в модуле `jewelry_client_metal_portal`: вкладка «Metal Account» с выпиской по §8.1, включается флагом `show_metal_account` в `jewelry.portal.access`

## 11. Модуль

| Параметр | Значение |
|---|---|
| Техническое имя | `jewelry_client_metal_accounts` |
| Зависимости | `jewelry_repair_base`, `jewelry_metal_accounting` |
| Новые модели | `jewelry.client.metal.account`, `jewelry.client.metal.transaction` |
| Расширяемые модели | `jewelry.repair.material.line`, `jewelry.repair.order`, `jewelry.metal.alloy` |

### 11.1. Принцип опциональности

Модуль должен быть полностью опциональным: если он не установлен, поведение всех существующих модулей остаётся идентичным текущему.

**Что безопасно без дополнительных условий:**
- Новые модели существуют только при установленном модуле
- Новые поля через `_inherit` не видны существующему коду если модуль не установлен
- Новые пункты меню и представления подключаются только при наличии модуля

**Единственное изменение в существующем коде:**

В `jewelry_repair_billing` необходимо выделить вычисление pricing weight материальной строки в отдельный overridable метод:

```python
# jewelry_repair_billing/models/billing.py
def _get_material_pricing_weight(self, line):
    """Возвращает вес строки как базу для расчёта суммы инвойса."""
    return line.weight + line.weight_loss
```

Существующая логика биллинга использует этот метод вместо inline-вычисления:

```python
pricing_weight = self._get_material_pricing_weight(line)
amount = pricing_weight * line.alloy_price_per_gram
```

Поведение при отсутствии нового модуля не меняется — метод возвращает то же значение что и раньше.

**Переопределение в новом модуле:**

```python
# jewelry_client_metal_accounts/models/billing_ext.py
def _get_material_pricing_weight(self, line):
    if line.client_metal_weight > 0:
        return line.invoice_pricing_weight  # уменьшенная база (потери пропорционально)
    return super()._get_material_pricing_weight(line)
```

При `client_metal_weight = 0` значение `invoice_pricing_weight = weight + weight_loss` — идентично текущему поведению.

**Таблица совместимости:**

| Сценарий | Без нового модуля | С новым модулем |
|---|---|---|
| Поля `client_metal_weight` и др. | не существуют | доступны |
| Биллинг строки без клиентского металла | `weight + weight_loss` | `weight + weight_loss` (то же) |
| Биллинг строки с клиентским металлом | невозможен | `invoice_pricing_weight` |
| Физический склад (writeoff) | без изменений | без изменений |
| Металл-счета клиентов | не существуют | работают |

## 12. Критерии приёмки

Контур считается реализованным корректно, если:
- можно создать металл-счёт клиента по каждому металлу
- пополнение через физический металл создаёт транзакцию `deposit_metal`
- пополнение через деньги создаёт транзакцию `deposit_cash` с пересчётом по котировке
- баланс счёта отображается в fine grams
- баланс информационно пересчитывается в настроенные сплавы
- на строке материала можно указать `client_metal_weight` (граммы физики с металл-счёта)
- `split_ratio`, `client_pricing_weight`, `invoice_pricing_weight` вычисляются автоматически
- потери распределяются пропорционально между металл-счётом и инвойсом
- при `client_metal_weight = 0` поведение строки идентично текущему
- физический склад всегда списывает только `weight` (без потерь) независимо от разбивки
- при биллинге создаются транзакции `debit_repair` с `weight_fine = client_pricing_weight × purity`
- денежный инвойс использует `invoice_pricing_weight` вместо полного `pricing_weight`
- сумма `client_pricing_weight + invoice_pricing_weight = weight + weight_loss` (баланс сходится)
- выписка по счёту показывает историю транзакций с остатком
- управленческий отчёт показывает позицию мастерской (физика − обязательства)
- клиент может сдать Gold585 и получить изделие в Gold750 без явной конвертации
