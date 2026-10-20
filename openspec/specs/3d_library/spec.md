# 3D Library — Библиотека 3D-моделей

## Purpose

Библиотека 3D-моделей ювелирных изделий в формате STL. Автоматически вычисляет объём и расчётный вес по каждому сплаву. Определяет посадочные места камней из геометрии модели. Хранит шаблоны услуг и материалов для быстрого заполнения заказов.

Модуль: `jewelry_3d_library`

Историческое ТЗ: `3D_LIBRARY_SPEC.md`

## Ключевые модели

### jewelry.model.3d — 3D-модель

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название модели |
| code | Char | Артикул |
| category_id | Many2one (jewelry.repair.item.type) | Категория (тип изделия) |
| preview_image | Image | Превью (авто из STL или загруженное) |
| notes | Text | Примечания |
| stl_file | Binary | STL-файл (attachment) |
| stl_filename | Char | Имя файла |
| volume_cm3 | Float | Объём (см³, из STL) |
| stone_seat_ids | One2many | Посадочные места камней |
| service_template_ids | One2many | Шаблоны услуг |
| material_template_ids | One2many | Шаблоны материалов |

### jewelry.model.3d.stone.seat — Посадочное место камня

| Поле | Тип | Описание |
|------|-----|----------|
| model_id | Many2one | Модель |
| diameter_mm | Float | Диаметр (мм) |
| count | Integer | Количество |
| standard_size_id | Many2one (jewelry.gem.standard.size) | Стандартный размер |
| gem_type_id | Many2one (jewelry.gem.type) | Тип камня |
| cut_shape | Selection | Форма огранки |

### jewelry.model.3d.service.template — Шаблон услуги

| Поле | Тип | Описание |
|------|-----|----------|
| model_id | Many2one | Модель |
| sequence | Integer | Порядок |
| product_id | Many2one (product.product, type=service) | Услуга |
| quantity | Float | Количество |
| price_unit | Float | Цена |

### jewelry.model.3d.material.template — Шаблон материала

| Поле | Тип | Описание |
|------|-----|----------|
| model_id | Many2one | Модель |
| sequence | Integer | Порядок |
| alloy_id | Many2one (jewelry.metal.alloy) | Сплав |
| weight | Float | Фактический вес (г, задаётся вручную) |
| weight_auto | Float | Расчётный вес = volume_cm3 × alloy.density |
| price_est | Float | Расчётная стоимость металла по текущей котировке |

### jewelry.metal.alloy (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| density | Float | Плотность сплава (г/см³) — используется для расчёта веса из объёма STL |

### jewelry.repair.order (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| model_3d_id | Many2one (jewelry.model.3d) | Связанная 3D-модель |

## Requirements

### Requirement: Парсинг STL-файла

#### Scenario: Вычисление объёма и превью

- GIVEN загружен STL-файл на форму модели
- WHEN нажимается "Parse STL"
- THEN через библиотеку trimesh вычисляется объём (cm³)
- AND если preview_image не заполнено — генерируется изометрическое превью (25° X, 45° Z, золотой цвет)
- AND превью рендерится через Pillow без GPU (painter's algorithm)
- AND если trimesh не установлен — объём = 0, превью не генерируется

#### Scenario: Определение посадочных мест камней

- GIVEN STL-файл с круглыми отверстиями под камни
- WHEN парсинг выполнен
- THEN алгоритм ищет круговые контуры в горизонтальном срезе (z = top 15%)
- AND группирует их по диаметру (шаг 0.1 мм)
- AND создаются stone_seat_ids (предыдущие удаляются)
- AND если diameter_mm совпадает со стандартным размером (±0.1 мм) → standard_size_id заполняется

#### Scenario: Заполнение шаблонов материалов

- GIVEN парсинг выполнен, material_template_ids пустые
- THEN создаётся по одной строке на каждый активный сплав в системе

---

### Requirement: Расчётный вес по сплаву

#### Scenario: Вычисление weight_auto

- GIVEN модель с volume_cm3 > 0
- AND сплав с заполненным density
- THEN weight_auto = volume_cm3 × density (г)
- AND price_est = weight_auto × rate.price_per_gram × purity (по текущей котировке)

---

### Requirement: 3D-просмотрщик

#### Scenario: Просмотр STL в браузере

- GIVEN загружен STL-файл
- WHEN нажимается "View 3D"
- THEN открывается клиентский action jewelry_3d_viewer с res_id
- AND модель рендерится в браузере (Three.js)

---

### Requirement: Загрузка шаблона в заказ

#### Scenario: Load from Model

- GIVEN заказ с выбранным model_3d_id
- WHEN нажимается "Load from Model"
- THEN из service_template_ids создаются строки услуг в заказе
- AND из material_template_ids создаются строки материалов (product = alloy.effective_material_product_id, weight = tmpl.weight)
- AND из stone_seat_ids (с заполненным gem_type_id) создаются строки камней

---

## TODO

- Автоматический просмотрщик в портале клиента (если будет реализован)
