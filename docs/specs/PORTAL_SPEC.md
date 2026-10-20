# Client Portal Spec — `jewelry_repair_portal`

## Цель

Клиентский портал для постоянных B2B-клиентов мастерской. Клиент видит статусы своих заказов в реальном времени без участия менеджера.

---

## Модуль

**Название:** `jewelry_repair_portal`  
**Зависимости:** `jewelry_repair_base`, `portal`  
**Подход:** наследование от `CustomerPortal`, стандартные шаблоны Odoo portal

---

## Роли и доступ

### Portal-пользователь

- Создаётся менеджером вручную через стандартный механизм Odoo:  
  карточка контрагента → кнопка **Grant Portal Access** → wizard `portal.wizard`
- Группа: `base.group_portal` (стандартная Odoo)
- Один пользователь может видеть заказы нескольких компаний

### Маппинг пользователь → клиенты

Новая модель `jewelry.portal.access`:

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | Many2one `res.users` | Portal-пользователь |
| `partner_id` | Many2one `res.partner` | Разрешённый контрагент |

- По умолчанию ни один партнёр не доступен
- Менеджер добавляет строки вручную в форме пользователя или отдельном списке
- `_sql_constraints`: уникальность пары `(user_id, partner_id)`

### ir.rule

Portal-пользователь видит только заказы партнёров из `jewelry.portal.access`:

```python
domain: [('partner_id', 'in', user.env['jewelry.portal.access']
    .search([('user_id', '=', user.id)]).mapped('partner_id').ids)]
```

---

## URL-структура

| URL | Описание |
|-----|----------|
| `/my/repairs` | Список активных заказов (вкладка по умолчанию) |
| `/my/repairs?tab=history` | История выданных заказов |
| `/my/repairs/<int:order_id>` | Карточка одного заказа |

---

## Страница: список заказов `/my/repairs`

### Вкладки

- **Active** — заказы со статусами: `draft`, `accepted`, `in_progress`, `ready`
- **History** — заказы со статусом: `delivered`

### Колонки таблицы

| Поле | Откуда |
|------|--------|
| Order # | `name` |
| Client | `partner_id.name` |
| Item | `item_type_id.name` |
| Description | `description` |
| Status | `state` |
| Deadline | `deadline_date` |
| Amount | `amount_total` |

- Сортировка по умолчанию: `deadline_date asc` для активных, `delivery_date desc` для истории
- Пагинация: стандартная через `pager()` из `portal.py`, 20 записей на страницу
- Строка кликабельна → переход на `/my/repairs/<id>`

---

## Страница: карточка заказа `/my/repairs/<id>`

### Поля

| Поле | Откуда |
|------|--------|
| Order # | `name` |
| Status | `state` |
| Item type | `item_type_id.name` |
| Description | `description` |
| Quantity | `quantity` |
| Deadline | `deadline_date` |
| Services | `service_line_ids` (название + цена) |
| Amount total | `amount_total` |
| Photo | `item_image` (если есть) |

- Материалы мастерской — **не показываем** (внутренняя информация)
- Имя мастера — **не показываем**
- Действия клиента — **только чтение**

### Навигация

Стандартные кнопки prev/next из `get_records_pager()` — переход между заказами.

---

## Шаблоны QWeb

Наследуемся от стандартных шаблонов портала:

```xml
<template id="portal_my_repairs" name="My Repairs">
    <t t-call="portal.portal_layout">
        ...
    </t>
</template>

<template id="portal_my_repair_detail" name="Repair Order Detail">
    <t t-call="portal.portal_layout">
        ...
    </t>
</template>
```

Счётчик в `/my/home` — наследование `portal_my_home_menu` и `portal_my_home`:

```xml
<!-- добавляет строку "Repair Orders (N)" в личный кабинет -->
<template id="portal_my_home_repair" inherit_id="portal.portal_my_home">
    ...
</template>
```

---

## Контроллер

```python
class JewelryRepairPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        # добавляет счётчик активных заказов в /my/home

    @route(['/my/repairs', '/my/repairs/page/<int:page>'], auth='user', website=True)
    def portal_my_repairs(self, tab='active', page=1, **kw):
        # возвращает список с пагинацией и вкладками

    @route(['/my/repairs/<int:order_id>'], auth='user', website=True)
    def portal_repair_detail(self, order_id, **kw):
        # проверяет доступ через ir.rule, возвращает карточку
```

Проверка доступа: стандартный `_document_check_access()` из `CustomerPortal` не подходит (он работает через `access_token`). Используем прямую проверку через ir.rule — если пользователь не имеет доступа, ORM бросит `AccessError` → 403.

---

## Управление доступом (бэкенд)

Менеджер управляет маппингом через отдельный список в бэкенде:

- Меню: **Jewelry Repair → Configuration → Portal Access**
- Форма: `user_id` + список разрешённых `partner_id`
- Или: вкладка в форме пользователя (решить при реализации — что удобнее)

---

## Структура модуля

```
jewelry_repair_portal/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── jewelry_portal_access.py      # модель маппинга
├── controllers/
│   ├── __init__.py
│   └── portal.py                     # JewelryRepairPortal(CustomerPortal)
├── views/
│   └── portal_templates.xml          # QWeb шаблоны
├── security/
│   ├── ir.model.access.csv
│   └── security.xml                  # ir.rule для portal-пользователей
└── i18n/
    └── ru.po
```

---

## За рамками этого спека (следующие итерации)

- Email-уведомление клиенту при смене статуса на `ready`
- Мультиязычный интерфейс (DE/FR для EU-рынка)
- Возможность клиента оставить комментарий к заказу
- QR-код на квитанции приёмки с прямой ссылкой на заказ
