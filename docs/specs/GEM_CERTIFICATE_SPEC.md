# Gem Certificate — Справочник сертификатов камней

## Цель

Хранение данных геммологических сертификатов (GIA, IGI, HRD и др.) с привязкой к строкам камней в заказах на ремонт.

---

## Модель `jewelry.gem.certificate`

### Идентификация

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | Char (required) | Номер отчёта / Report Number (напр. LG763615904) |
| `lab` | Selection | Лаборатория: GIA, IGI, HRD, AGS, EGL, CIBJO, Other |
| `lab_other` | Char | Название лаборатории (только если lab = Other) |
| `cert_date` | Date | Дата выдачи сертификата |

### Характеристики камня

| Поле | Тип | Описание |
|------|-----|----------|
| `gem_type_id` | Many2one `jewelry.gem.type` | Тип камня |
| `description` | Char | Текстовое описание (напр. "Laboratory Grown Diamond") |
| `origin` | Selection | Происхождение: Natural / Laboratory Grown |
| `shape_cut` | Char | Форма и стиль огранки (напр. "Cut Cornered Square Modified Brilliant") |
| `dim_1` | Float (мм) | Размер 1 |
| `dim_2` | Float (мм) | Размер 2 |
| `depth` | Float (мм) | Глубина |
| `carat_weight` | Float (4 знака) | Вес в каратах |

### Грейдинг 4C

| Поле | Тип | Описание |
|------|-----|----------|
| `color_grade` | Char | Цвет (напр. D, E, F, G... или Fancy) |
| `clarity_grade` | Char | Чистота (напр. FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1) |
| `cut_grade` | Selection | Огранка: Excellent / Very Good / Good / Fair / Poor |

### Дополнительный грейдинг

| Поле | Тип | Описание |
|------|-----|----------|
| `polish` | Selection | Полировка: Excellent / Very Good / Good / Fair / Poor |
| `symmetry` | Selection | Симметрия: Excellent / Very Good / Good / Fair / Poor |
| `fluorescence` | Selection | Флуоресценция: None / Faint / Medium / Strong / Very Strong |

### Дополнительно (для lab grown)

| Поле | Тип | Описание |
|------|-----|----------|
| `lab_grown_type` | Selection | Тип синтеза: CVD / HPHT |
| `type_classification` | Char | Классификация (напр. "Type IIa") |
| `comments` | Text | Комментарии с сертификата |

### Медиа и связи

| Поле | Тип | Описание |
|------|-----|----------|
| `cert_image` | Binary (attachment) | Фото сертификата |
| `cert_image_name` | Char | Имя файла фото |
| `gem_line_ids` | One2many `jewelry.repair.gem.line` | Строки камней, использующие этот сертификат |

---

## Связь с заказом на ремонт

В модели `jewelry.repair.gem.line` добавлено поле:

```
certificate_id = Many2one(jewelry.gem.certificate, ondelete=set null)
```

- Необязательное поле — сертификат можно не указывать
- Колонка "Certificate" в таблице камней заказа (скрыта по умолчанию, `optional="hide"`)
- При удалении сертификата поле в строке обнуляется (`set null`)

---

## Поиск заказа по номеру сертификата

В search view `jewelry.repair.order` добавлено поле "Certificate No.":

```xml
<field name="gem_line_ids" string="Certificate No."
       filter_domain="[('gem_line_ids.certificate_id.name', 'ilike', self)]" />
```

Позволяет найти заказ по полному или частичному номеру сертификата.

---

## AI-парсинг фото

Кнопка **"Parse from Image"** на форме сертификата вызывает метод `action_parse_from_image`:

1. Проверяет наличие фото (`cert_image`)
2. Берёт API-ключ из `ir.config_parameter` → ключ `anthropic.api_key`
3. Отправляет изображение в Claude API (vision) с запросом вернуть JSON
4. Парсит ответ и заполняет поля сертификата
5. Показывает уведомление об успехе

### Настройка

- Установить пакет: `pip install anthropic`
- В Odoo: Настройки → Технические → Системные параметры → создать запись:
  - Ключ: `anthropic.api_key`
  - Значение: `sk-ant-...`

### Graceful degradation

Если пакет `anthropic` не установлен или ключ не настроен — кнопка выбрасывает понятное `UserError` с инструкцией, не ломая остальной функционал.

---

## Права доступа

| Роль | Читать | Создавать | Редактировать | Удалять |
|------|--------|-----------|---------------|---------|
| Мастер (master) | ✓ | — | — | — |
| Приёмщик (receptionist) | ✓ | ✓ | ✓ | — |
| Менеджер (manager) | ✓ | ✓ | ✓ | ✓ |
| Системный | ✓ | ✓ | ✓ | ✓ |

---

## Расположение в меню

`Catalogs → Certificates` (sequence 28, между Gem Types и Metal Alloys)

---

## Источник данных — пример IGI LG763615904

| Поле | Значение |
|------|----------|
| Report Number | LG763615904 |
| Lab | IGI |
| Date | 2026-01-19 |
| Description | Laboratory Grown Diamond |
| Origin | Laboratory Grown |
| Shape & Cut | Cut Cornered Square Modified Brilliant |
| Dim 1 | 10.02 мм |
| Dim 2 | 9.68 мм |
| Depth | 6.09 мм |
| Carat Weight | 5.53 ct |
| Color Grade | F |
| Clarity Grade | VVS2 |
| Polish | Excellent |
| Symmetry | Excellent |
| Fluorescence | None |
| Growth Type | CVD |
| Type Classification | Type IIa |
