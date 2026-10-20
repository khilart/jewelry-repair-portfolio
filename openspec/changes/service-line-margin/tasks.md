# Tasks: Service Line Margin

## 1. Модель (`jewelry_repair_base`)

- [x] 1.1 Поле `base_price` на `jewelry.repair.service.line` — Float, `digits=(16, 2)`
- [x] 1.2 `base_amount` — compute+store от `outsource_cost`, `base_price`, `total_quantity`
- [x] 1.3 `margin` — compute+store от `subtotal` и `base_amount`
- [x] 1.4 `_onchange_product_id` проставляет `base_price` тем же значением, что и `price_unit`
      (включая сброс в 0 при снятии продукта)
- [x] 1.5 `create()` подставляет `base_price = price_unit`, если поле не передано

## 2. UI

- [x] 2.1 Колонки `Base Price` (readonly), `Base Amount`, `Margin` в
      `view_jewelry_repair_service_line_costs_tree`, с итогами по суммам

## 3. Миграция

- [x] 3.1 Версия модуля → `17.0.1.2.0`
- [x] 3.2 `migrations/17.0.1.2.0/post-fill-service-base-price.py`: `base_price = price_unit`
      там, где база пустая (имя файла строго через дефис)

## 4. Роль Director

- [x] 4.1 Ярлык группы → `Jewelry Repair / Observer (read-only)`, xml id не трогаем
- [x] 4.2 Правило зафиксировано в `CLAUDE.md` (таблица ролей) и `DECISIONS.md`
- [x] 4.3 Расхождение ACL с фактическим read-only вынесено задачей в `TODO.md`

## 5. Переводы

- [x] 5.1 `ru.po` модуля `jewelry_repair_base`: Base Price, Base Amount, Margin, новое имя группы

## 6. Тесты

- [x] 6.1 База снимается при выборе услуги и равна `price_unit`
- [x] 6.2 Правка `price_unit` не меняет `base_price`, маржа пересчитывается
- [x] 6.3 Продажа ниже базы даёт отрицательную маржу
- [x] 6.4 `outsource_cost` перебивает базу и трактуется как сумма за строку
- [x] 6.5 Снятие `outsource_cost` возвращает базу к `base_price × total_quantity`
- [x] 6.6 Строка, созданная без `base_price`, получает её из `price_unit`
