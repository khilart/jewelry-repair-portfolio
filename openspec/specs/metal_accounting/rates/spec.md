# Metal Accounting / Rates — Котировки металла

## Purpose

Регистр исторических котировок металла (цена за грамм чистого металла). Используется для автоматического расчёта стоимости материальных строк заказа и строк металлодокументов.

Модуль: `jewelry_metal_accounting`

Историческое ТЗ: `METAL_RATES_SPEC.md`

## Ключевые модели

### jewelry.metal.rate — Котировка металла

| Поле | Тип | Описание |
|------|-----|----------|
| metal_id | Many2one (jewelry.metal) | Металл |
| price_per_gram | Monetary | Цена за грамм чистого металла |
| currency_id | Many2one | Валюта |
| effective_at | Datetime | Дата/время вступления в силу |
| company_id | Many2one | Компания |
| price_18k | Monetary | Цена за грамм 18k (= price_per_gram × 0.750) |
| price_14k | Monetary | Цена за грамм 14k (= price_per_gram × 0.585) |
| price_9k | Monetary | Цена за грамм 9k (= price_per_gram × 0.375) |
| notes | Text | Примечания |
| active | Boolean | Активна |

## Requirements

### Requirement: Регистр котировок

Система хранит исторические котировки металла. Для каждого момента времени используется последняя котировка, вступившая в силу не позже указанной даты.

#### Scenario: Поиск котировки на дату

- GIVEN металл, дата/время, компания
- WHEN запрашивается котировка
- THEN возвращается последняя котировка с effective_at ≤ указанной даты для данного металла и компании
- AND если котировки нет — возвращается пустое (ошибка при сохранении строки)

#### Scenario: Информационные цены по пробам

- GIVEN котировка с price_per_gram
- THEN автоматически вычисляются: price_18k, price_14k, price_9k (только для справки)

---

### Requirement: Расчёт цены металлического материала в заказе

Формула: `price_unit = rate_per_gram × alloy.purity × (weight + weight_loss) / quantity`

Где:
- `rate_per_gram` — цена за грамм чистого металла из котировки
- `alloy.purity` — коэффициент пробы (например 0.585 для 14k)
- `weight` — вес металла в данной строке (г)
- `weight_loss` — возвратные потери = weight × repair_material_return_loss_percent / 100
- `quantity` — количество единиц

#### Scenario: Котировка на дату материальной строки

- GIVEN строка материала с alloy_id и weight и rate_datetime
- WHEN пересчитывается цена
- THEN берётся котировка на rate_datetime строки (или metal_rate_at заказа как fallback)
- AND rate_price_per_gram фиксируется в строке
- AND price_unit = rate_price_per_gram × purity × (weight + weight_loss) / quantity

#### Scenario: Валидация отсутствия котировки

- GIVEN строка с alloy_id и weight, но котировка не найдена
- THEN строку нельзя сохранить (ValidationError)

---

### Requirement: Расчёт стоимости receipts в металлодокументах

Для строк типа receipt в jewelry.metal.document.line:

`amount = rate_per_gram × alloy.purity × weight`

#### Scenario: Информационная стоимость receipt

- GIVEN строка металлодокумента типа receipt с alloy_id, weight, rate_datetime
- THEN amount вычисляется автоматически (информационно, не для выставления счёта)
