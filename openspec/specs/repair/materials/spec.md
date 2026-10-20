# Repair / Materials — Материалы

## Purpose

Учёт материалов мастерской в заказах ремонта. Строки материалов поддерживают автоматическое ценообразование на основе котировок металла, флаги для списания со склада, возврата и включения в счёт.

Модуль: `jewelry_repair_base`

Историческое ТЗ (черновик): `MATERIALS_SPEC_DRAFT.md`

## Критичное разделение

```
Материалы клиента (информационно, вес изделия)  ≠  Материалы мастерской (склад + в счёт)
```

## Requirements

### Requirement: Строки материалов мастерской

#### Scenario: Включение в счёт

- GIVEN строка материала с `include_in_invoice = True`
- WHEN создаётся инвойс через биллинг-батч
- THEN стоимость строки включается в инвойс

#### Scenario: Металлические материалы — автоматическая цена

- GIVEN строка с alloy_id и weight > 0
- THEN система автоматически рассчитывает price_unit по формуле:
  `price_unit = rate_per_gram × purity × (weight + weight_loss) / quantity`
- AND weight_loss = weight × repair_material_return_loss_percent / 100
- AND rate_datetime берётся из строки или из metal_rate_at заказа
- AND при отсутствии котировки — строку нельзя сохранить

#### Scenario: Привязка к операции

- GIVEN строка материала с заполненным order_operation_id
- THEN строка отображается в материалах операции (вкладка Materials на форме операции мастера)
- AND source_storage_id заполняется автоматически из executor_metal_storage_id операции

#### Scenario: Редактирование суммы менеджером

- GIVEN subtotal_editable=True (только для менеджера)
- WHEN менеджер напрямую изменяет subtotal
- THEN price_unit пересчитывается = subtotal / quantity

---

### Requirement: Флаги строки материала

| Флаг | Поведение |
|------|-----------|
| `consume_from_stock` | Материал будет списан со склада при синхронизации металлодокумента |
| `source_storage_id` | Склад списания (обязателен при consume_from_stock) |
| `return_to_storage` | Остаток металла возвращается на склад |
| `return_storage_id` | Склад возврата (обязателен при return_to_storage) |
| `is_auto_calculated` | Строка создана автоматически металлорасчётом (readonly) |

---

### Requirement: Привязка по умолчанию из продукта

При добавлении продукта в строку автоматически устанавливаются:
- include_in_invoice из repair_material_default_invoice
- consume_from_stock из repair_material_default_consume
- uom_id из product.uom_id
- price_unit из lst_price (для не-металлических)

---

### Requirement: Вес материала обязателен (если настроено)

- GIVEN продукт с repair_material_requires_weight=True
- AND weight = 0
- THEN ошибка при сохранении строки
