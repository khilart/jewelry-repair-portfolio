# Metal Accounting / Loss — Потери металла

## Purpose

Учёт весовых потерь металла по производственным зонам (work areas) в рамках заказа. Потери рассчитываются автоматически на основании весов, введённых мастерами. Отдельно ведётся учёт потерь материалов через jewelry.metal.loss.

Модуль: `jewelry_metal_accounting` + `jewelry_repair_base`

Историческое ТЗ: `LOSS_ACCOUNTING_SPEC.md`

## Ключевые модели

### jewelry.work.area — Производственная зона

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название |
| sequence | Integer | Порядок |
| is_casting | Boolean | Зона литья: weight_in берётся из потреблённых материалов, не из weight_before |

### jewelry.order.area.loss — Потери по зоне

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one (jewelry.repair.order) | Заказ |
| area_id | Many2one (jewelry.work.area) | Зона |
| weight_in | Float | Вес на входе зоны (г, скорректированный) |
| weight_out | Float | Вес на выходе зоны (г, скорректированный) |
| loss | Float | weight_in − weight_out |
| loss_percent | Float | loss / weight_in × 100 |

### jewelry.order.client.loss — Потери по клиенту (SQL View)

Показывает потери металла на уровне заказа: received_weight, metal_delivered_weight (delivered − gems), loss, loss_percent. Только для выданных заказов.

### jewelry.metal.loss — Потеря материала

Создаётся автоматически при завершении операции для каждой строки материала с weight_loss > 0. Хранит: тип потери, сплав, вес, хранилище, источник.

## Requirements

### Requirement: Расчёт потерь по зонам (area loss)

#### Scenario: Триггер расчёта

- GIVEN заказ переходит в `ready` (все операции done)
- OR менеджер изменяет delivered_weight в статусах ready/delivered
- THEN вызывается пересчёт area_loss_ids (предыдущие удаляются, создаются новые)

#### Scenario: Режим отслеживания

- GIVEN weight_tracking_mode = disabled
- THEN area_loss_ids очищаются, расчёт не производится
- GIVEN weight_tracking_mode = new_product_only
- THEN расчёт только для заказов с new_product_manufacturing=True
- GIVEN weight_tracking_mode = all
- THEN расчёт для всех заказов

#### Scenario: Алгоритм расчёта weight_in

Для каждой зоны:
- Обычная зона: weight_in = weight_before первой операции зоны
  - минус: gem_weight_total_g (если зона идёт после gem-setting зоны)
  - минус: сумма материалов-добавок из предыдущих зон (cumulative_material)
  - плюс: сумма возвращённых материалов из предыдущих зон (cumulative_return)
- Зона литья (is_casting) при new_product_manufacturing: weight_in = суммарный вес потреблённых материалов в этой зоне

#### Scenario: Алгоритм расчёта weight_out

Для каждой зоны:
- weight_out = weight_before первой операции следующей зоны (или delivered_weight для последней)
  - минус: gem_weight_total_g (если зона ≥ gem-setting зоны)
  - минус: cumulative_material[i]
  - плюс: cumulative_return[i]

#### Scenario: Корректировка на вес камней (gem setting)

- GIVEN зона, содержащая операции с is_gem_setting=True
- THEN gem_weight_total_g вычитается из weight_out этой зоны и из weight_in/out всех последующих
- (камни входят в состав изделия — их вес исключается из металлового учёта)

#### Scenario: Материалы-добавки

- GIVEN материальная строка с consume_from_stock=True, weight > 0, привязана к операции зоны
- AND это НЕ зона литья (is_casting) для нового изделия
- THEN вес этого материала накапливается и вычитается из последующих зон

#### Scenario: Возвратные материалы

- GIVEN материальная строка с return_to_storage=True, weight > 0, привязана к операции зоны
- THEN вес возврата накапливается и прибавляется к последующим зонам

---

### Requirement: Потери по участкам на форме заказа

#### Scenario: Вкладка Metal Loss by Area

- GIVEN заказ с weight_tracking_enabled=True и рассчитанными area_loss_ids
- THEN вкладка "Metal Loss by Area" видна и отображает таблицу
- GIVEN weight_tracking_enabled=False
- THEN вкладка скрыта

---

### Requirement: Отчёт металлопотерь (Metal Loss Report)

Вызывается из визарда (MetalLossReportWizard): выбор периода, группировка по типу операции или по исполнителю.

#### Scenario: Группировка по операции

- GIVEN период и выбрана группировка "By Operation Type"
- THEN для каждого типа операции суммируются потери (weight_before_op − weight_before_next_op с поправками на камни)
- AND gem-setting операции выводятся отдельным блоком с весом камней (не как потеря)

#### Scenario: Группировка по исполнителю

- GIVEN группировка "By Executor"
- THEN суммируются потери по каждому assigned_user_id (gem-setting блоки исключаются)

---

### Requirement: Потери материалов (jewelry.metal.loss)

Отдельный регистр потерь, возникающих при работе с материалами (weight_loss = weight × return_loss_percent / 100).

- Создаются автоматически при завершении (Done) каждой операции
- Удаляются при откате операции (Return to Rework, Reset to Pending, Cancel)
- Требуют наличия executor_metal_storage_id на операции — иначе ошибка
- Доступны на операции через smart button "Metal Loss Entries"
