# Delta: Service Line Margin — базовая цена и маржа строки услуги

## MODIFIED

### Модель: jewelry.repair.service.line — Строка услуги

Добавлены поля:

| Поле | Тип | Описание |
|------|-----|----------|
| base_price | Float | Базовая цена за единицу — снимок цены на момент выбора услуги |
| base_amount | Float (compute, store) | База суммой: `outsource_cost`, если указан, иначе `base_price × total_quantity` |
| margin | Float (compute, store) | `subtotal − base_amount` |

### Requirement: Роли и доступ

Строка таблицы ролей:

| Роль | Что делает |
|------|-----------|
| Наблюдатель (Observer, xml id `group_jewelry_repair_director`) | Только чтение. Для `jewelry.repair.order` обеспечено `write()`-оверрайдом; ACL прочих моделей роли приведены к read-only не полностью |

## ADDED

### Requirement: Базовая цена услуги

Строка услуги хранит базовую цену — то, во что услуга обходится мастерской, — чтобы
разницу с ценой продажи можно было использовать для расчёта мотивации менеджера.

Базовая цена не участвует в счёте, биллинге и на портале: это внутренняя аналитика.

#### Scenario: База снимается при выборе услуги

- GIVEN новая строка услуги в заказе
- WHEN выбран продукт-услуга
- THEN `price_unit` заполняется ценой клиента (`jewelry.repair.client.price.final_price`),
  а при её отсутствии — прайсом продукта (`lst_price`)
- AND `base_price` получает **то же самое** значение

#### Scenario: Правка цены не трогает базу

- GIVEN строка услуги с `price_unit = 3 000` и `base_price = 3 000`
- WHEN менеджер меняет `price_unit` на `3 500`
- THEN `base_price` остаётся `3 000`
- AND `margin` становится `500 × total_quantity`

#### Scenario: Продажа ниже базы даёт отрицательную маржу

- GIVEN строка услуги с `base_price = 3 000`, `total_quantity = 1`
- WHEN менеджер ставит `price_unit = 2 400`
- THEN `margin = −600`

#### Scenario: Смена продукта переснимает базу

- GIVEN строка услуги с уже проставленной `base_price`
- WHEN в строке выбран другой продукт-услуга
- THEN `base_price` и `price_unit` заполняются заново по новому продукту

#### Scenario: Строка создана в обход onchange

- GIVEN строка услуги создаётся кодом или импортом с указанным `price_unit` и без `base_price`
- WHEN запись создаётся
- THEN `base_price` подставляется равной `price_unit`
- AND `margin` равна нулю, а не всей выручке строки

---

### Requirement: База по аутсорсным услугам

Если услуга отдана на аутсорс, себестоимостью считается фактическая стоимость аутсорса,
а не снимок прайса.

#### Scenario: Аутсорс перебивает базовую цену

- GIVEN строка услуги с `base_price = 4 000`, `total_quantity = 1`, `subtotal = 12 000`
- WHEN менеджер указывает `outsource_cost = 8 000`
- THEN `base_amount = 8 000`
- AND `margin = 4 000`

#### Scenario: Аутсорс — сумма за строку, а не за единицу

- GIVEN строка услуги с `total_quantity = 3` и `outsource_cost = 9 000`
- THEN `base_amount = 9 000` (не `27 000`)

#### Scenario: Аутсорс снят

- GIVEN строка услуги с `outsource_cost = 8 000`
- WHEN `outsource_cost` обнуляется
- THEN `base_amount` снова считается как `base_price × total_quantity`

---

### Requirement: Маржа на вкладке Costs

#### Scenario: Колонки видны в заказе

- GIVEN заказ со строками услуг
- WHEN открыта вкладка **Costs**
- THEN в таблице есть колонки `Base Price` (readonly), `Base Amount` и `Margin`
- AND по `Base Amount` и `Margin` выводятся итоги по колонке
- AND дополнительных ограничений по группам на колонки нет — как и у `Outsource Cost`

---

### Requirement: База для существующих строк

#### Scenario: Миграция заполняет базу по факту продажи

- GIVEN строки услуг, созданные до появления поля
- WHEN модуль обновляется
- THEN строкам с пустой `base_price` проставляется `base_price = price_unit`
- AND маржа по историческим заказам получается нулевой
