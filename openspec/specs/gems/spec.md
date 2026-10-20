# Gems — Сертификаты и учёт камней

## Purpose

Справочник сертификатов камней (GIA/IGI/HRD и другие лаборатории), учёт камней в заказах ремонта, автоматическое распознавание данных с фото сертификата через Claude API. Генерация услуг закрепки по настроенным правилам.

Модуль: `jewelry_repair_base`

Историческое ТЗ: `GEM_CERTIFICATE_SPEC.md`

## Ключевые модели

### jewelry.gem.type — Тип камня

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название (бриллиант, изумруд и т.д.) |
| active | Boolean | Активен |
| parse_keywords | Char | Ключевые слова через запятую для маппинга при парсинге |
| product_id | Many2one (product.product) | Продукт для счёта по умолчанию |
| standard_size_ids | One2many | Стандартные размеры |
| setting_rule_ids | One2many | Правила закрепки |

### jewelry.gem.standard.size — Стандартный размер камня

| Поле | Тип | Описание |
|------|-----|----------|
| gem_type_id | Many2one | Тип камня |
| cut_shape | Selection | Форма огранки (round/oval/princess/cushion/emerald/radiant/pear/marquise/heart/asscher) |
| dim_1 | Float | Первый размер (мм) |
| dim_2 | Float | Второй размер (мм, для несимметричных) |
| weight_ct | Float | Вес в каратах |
| weight_g | Float | Вес в граммах (weight_ct × 0.2) |
| label | Char | Читаемый размер (вычислен) |

### jewelry.gem.setting.rule — Правило закрепки

| Поле | Тип | Описание |
|------|-----|----------|
| gem_type_id | Many2one | Тип камня |
| service_product_id | Many2one (product.product) | Услуга закрепки |
| weight_ct_from | Float | От (каратов) |
| weight_ct_to | Float | До (каратов, 0 = без ограничения) |

### jewelry.gem.certificate — Сертификат камня

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Номер отчёта (уникален) |
| lab | Selection | GIA / IGI / HRD / AGS / EGL / CIBJO / other |
| lab_other | Char | Название лаборатории (если lab=other) |
| cert_date | Date | Дата сертификата |
| gem_type_id | Many2one | Тип камня |
| description | Char | Описание |
| origin | Selection | natural / lab_grown |
| shape_cut | Char | Форма и огранка |
| dim_1 / dim_2 / depth | Float | Размеры (мм) |
| carat_weight | Float | Вес в каратах |
| color_grade | Char | Цвет (D-Z) |
| clarity_grade | Char | Чистота |
| cut_grade / polish / symmetry | Selection | excellent/very_good/good/fair/poor |
| fluorescence | Selection | none/faint/medium/strong/very_strong |
| lab_grown_type | Selection | cvd / hpht |
| type_classification | Char | Классификация типа |
| comments | Text | Комментарии |
| cert_image | Binary | Фото сертификата |
| gem_line_ids | One2many | Строки в заказах, где использован |

### jewelry.repair.gem.line — Строка камня в заказе

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one | Заказ |
| gem_type_id | Many2one | Тип камня |
| cut_shape | Selection | Форма огранки |
| standard_size_id | Many2one (jewelry.gem.standard.size) | Стандартный размер |
| quantity | Integer | Количество камней |
| weight_ct | Float | Вес одного камня (каратов) |
| total_weight_ct | Float | Суммарный вес (qty × weight_ct) |
| total_weight_g | Float | Суммарный вес в граммах (qty × weight_ct × 0.2) |
| certificate_id | Many2one (jewelry.gem.certificate) | Сертификат |
| price_per_ct | Monetary | Цена за карат |
| price_unit | Monetary | Цена за штуку |
| subtotal | Monetary | qty × price_per_ct × weight_ct (или qty × price_unit если нет price_per_ct) |
| include_in_invoice | Boolean | Включить в счёт |
| product_id | Many2one (product.product) | Продукт для счёта |
| currency_id | Many2one | Валюта (из заказа) |

### jewelry.gem.cert.parse.wizard — Визард парсинга сертификата (Transient)

| Поле | Тип | Описание |
|------|-----|----------|
| order_id / gem_line_id | Many2one | Контекст (заказ или строка) |
| cert_image | Binary | Загруженное фото |
| state | Selection | upload / duplicate |
| existing_cert_id | Many2one | Найденный дубликат |
| pending_cert_vals | Text | JSON с данными нового сертификата |

## Requirements

### Requirement: Справочник сертификатов камней

#### Scenario: Создание сертификата вручную

- GIVEN пользователь открывает справочник Certificates
- WHEN заполняет данные (lab, report_number, 4C, etc.)
- THEN создаётся запись jewelry.gem.certificate

#### Scenario: Парсинг сертификата из фото

- GIVEN загружено изображение сертификата на форме certificate или через визард
- WHEN нажимается "Parse from Image" (форма) или в визарде после загрузки фото
- THEN изображение отправляется в Claude API (claude-sonnet-4-6)
- AND все данные сертификата автоматически заполняются: report_number, lab, 4C, polish, symmetry, fluorescence, dimensions, origin, comments
- AND если lab = нестандартная → lab=other, lab_other=название
- AND тип камня подбирается по parse_keywords из jewelry.gem.type

#### Scenario: Обнаружен дубликат сертификата

- GIVEN парсинг вернул report_number, уже существующий в базе
- WHEN визард переходит в состояние "Duplicate Found"
- THEN пользователю предлагается: "Use Existing" (привязать существующий) или "Create New" (создать новый с тем же номером)

#### Scenario: Маппинг типа камня

- GIVEN сертификат с description "Diamond round 1.20ct"
- WHEN парсинг завершён
- THEN gem_type_id заполняется по совпадению parse_keywords любого gem.type

---

### Requirement: Строки камней в заказе

#### Scenario: Ценообразование камня

- GIVEN строка с заполненным price_per_ct и weight_ct
- THEN subtotal = qty × price_per_ct × weight_ct
- AND price_unit автоматически = price_per_ct × weight_ct
- AND при изменении price_unit → price_per_ct пересчитывается

#### Scenario: Заполнение строки из сертификата

- GIVEN пользователь выбирает certificate_id в строке
- WHEN onchange срабатывает
- THEN gem_type_id, weight_ct, cut_shape заполняются из сертификата
- AND total_weight_ct = weight_ct × quantity
- AND если price_per_ct уже заполнен → price_unit пересчитывается

#### Scenario: Выбор стандартного размера

- GIVEN выбран gem_type_id и cut_shape
- WHEN пользователь выбирает standard_size_id
- THEN weight_ct заполняется из стандартного размера

---

### Requirement: Визард парсинга из таблицы камней

#### Scenario: Кнопка-фото в строке

- GIVEN строка камня в заказе
- WHEN пользователь нажимает кнопку камеры (fa-camera) в строке
- THEN открывается визард парсинга в контексте существующей строки
- AND после парсинга строка обновляется (certificate_id, gem_type_id, weight_ct, cut_shape)

#### Scenario: Кнопка "Add from Certificate"

- GIVEN форма заказа, вкладка Stones
- WHEN пользователь нажимает "Add from Certificate"
- THEN открывается визард без привязки к строке (order_id контекст)
- AND создаётся новая строка камня после парсинга

---

### Requirement: Генерация услуг закрепки

#### Scenario: Generate Setting Services

- GIVEN заказ с камнями, правила закрепки настроены на gem.type
- WHEN нажимается "Generate Setting Services"
- THEN для каждого камня ищется setting_rule по gem_type_id и весу weight_ct ∈ [weight_ct_from, weight_ct_to)
- AND если правило не найдено — ошибка с перечислением непокрытых камней
- AND ценообразование fixed: одна строка услуги на правило, total_qty = сумма qty всех камней × quantity заказа
- AND ценообразование per_carat: отдельная строка на каждую gem_line, price_unit = base_price × weight_ct

---

### Requirement: Стандартные размеры

Кнопка "Load Standard Round Brilliant Sizes" на форме gem.type загружает промышленный стандарт размеров бриллиантов (0.8мм / 0.0015ct ... 17.65мм / 20ct) для огранки round.

---

### Requirement: Учёт веса камней в заказе

- gem_weight_total_g = сумма total_weight_g всех строк камней
- received_with_gems_g = received_weight + gem_weight_total_g
- metal_delivered_weight = delivered_weight − gem_weight_total_g (чистый вес металла)
- certificate_numbers = список номеров сертификатов (поисковый индекс)

---

### Requirement: Камни в портале клиента

#### Scenario: Отображение камней

- GIVEN заказ с камнями, видимый клиенту на портале
- WHEN show_uninvoiced_gems=True на portal_access → показываются все камни
- WHEN show_uninvoiced_gems=False → только с include_in_invoice=True
- THEN таблица: тип камня, сертификат (ссылка), кол-во, вес (ct), сумма

#### Scenario: Модальное окно сертификата

- GIVEN клиент нажимает ссылку сертификата
- THEN Bootstrap 5 modal с полными данными: lab, date, 4C, polish/symmetry/fluorescence, dimensions, comments
