# Спецификация: Telegram-уведомления (`jewelry_telegram_notify`)

## 1. Назначение

Модуль отправляет push-уведомления в Telegram участникам процесса ремонта.
Целевая аудитория — мастера, работающие с телефоном, а также менеджеры и приёмщики.

Уведомления покрывают два типа событий:
- **Реального времени** — срабатывают при изменении состояния заказа или операции
- **По расписанию** — cron проверяет дедлайны и просроченные заказы раз в час

---

## 2. Модуль

**Название:** `jewelry_telegram_notify`  
**Зависимости:** `jewelry_repair_base`  
**Тип:** опциональный, устанавливается поверх базового модуля

---

## 3. Настройки

### 3.1. Где хранятся

Все настройки хранятся в `ir.config_parameter` (ключи вида `jewelry_telegram.%`).
Форма редактирования — вкладка **Telegram** в `Settings → Technical → Telegram Notifications`
(отдельный пункт меню в разделе Technical, доступен только администратору).

### 3.2. Параметры

| Ключ | Тип | Описание |
|------|-----|----------|
| `jewelry_telegram.bot_token` | Char | Токен бота от @BotFather |
| `jewelry_telegram.notify_operation_assigned` | Boolean | Новая операция назначена мастеру |
| `jewelry_telegram.notify_deadline_approaching` | Boolean | Дедлайн заказа приближается |
| `jewelry_telegram.notify_order_overdue` | Boolean | Заказ просрочен |
| `jewelry_telegram.notify_order_ready` | Boolean | Заказ перешёл в Ready (менеджеру) |
| `jewelry_telegram.notify_order_delivery_ready` | Boolean | Заказ готов к выдаче (приёмщику) |
| `jewelry_telegram.deadline_threshold_hours` | Integer | За сколько часов до дедлайна уведомлять (по умолчанию: 24) |

### 3.3. Форма настроек

```
┌─────────────────────────────────────────────────────┐
│ Telegram Notifications                               │
├─────────────────────────────────────────────────────┤
│ Bot Token  [________________________________] [Test] │
│                                                     │
│ Notifications                                       │
│ ☑ New operation assigned to master                  │
│ ☑ Order deadline approaching                        │
│   Threshold: [24] hours before deadline             │
│ ☑ Order overdue (past deadline)                     │
│ ☑ Order moved to Ready                              │
│ ☑ Order ready for delivery                          │
└─────────────────────────────────────────────────────┘
```

Кнопка **Test** отправляет тестовое сообщение от имени текущего пользователя
(если у него задан `telegram_chat_id`).

---

## 4. Привязка пользователя к боту

### 4.1. Поле на пользователе

На модели `res.users` добавляется поле:

```
telegram_chat_id = fields.Char(string="Telegram Chat ID")
```

Отображается в форме пользователя (`Settings → Users`) в новой группе **Telegram**.

### 4.2. Как мастеру получить свой Chat ID

1. Мастер открывает Telegram и пишет боту любое сообщение (например, `/start`)
2. Мастер открывает в браузере: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. В ответе находит своё `chat.id`
4. Передаёт число менеджеру — тот вводит в карточку пользователя

Либо: мастер пишет боту `@userinfobot` — тот сразу отвечает своим chat_id.

> Автоматическая привязка через webhook выходит за рамки MVP. Ручной ввод достаточен.

---

## 5. События и получатели

### 5.1. Новая операция назначена мастеру

**Триггер:** в `action_start` или при переходе операции в состояние, доступное для старта следующим мастером (когда предыдущая завершена и `_sync_operation_flow` активирует следующую).

**Получатель:** `operation.assigned_user_id` (или `executor_id.user_id`)

**Текст:**
```
🔨 Новая задача

Заказ: {order.name}
Изделие: {order.item_type_id.name}
Операция: {operation.operation_id.name}
Клиент: {order.partner_id.name}
Дедлайн: {order.deadline_date}
```

**Условие отправки:** `notify_operation_assigned = True` и у пользователя задан `telegram_chat_id`

---

### 5.2. Дедлайн заказа приближается

**Триггер:** cron раз в час

**Логика:**
- Заказы в статусе `in_progress` или `ready`
- `deadline_date` попадает в окно `[now, now + threshold_hours]`
- Уведомление отправляется **один раз** — флаг `deadline_notified` на заказе предотвращает повтор

**Получатели:**
- Мастера активных операций заказа (незавершённых)
- Менеджер (из группы `group_jewelry_repair_manager`) — TODO: либо ответственный пользователь

**Текст для мастера:**
```
⏰ Приближается дедлайн

Заказ: {order.name}
Изделие: {order.item_type_id.name}
Операция: {operation.operation_id.name}
Дедлайн: {order.deadline_date}
```

**Текст для менеджера:**
```
⏰ Дедлайн скоро

Заказ: {order.name} — {order.item_type_id.name}
Клиент: {order.partner_id.name}
Дедлайн: {order.deadline_date}
Статус: {order.state}
```

---

### 5.3. Заказ просрочен

**Триггер:** cron раз в час

**Логика:**
- Заказы в статусе `in_progress` или `ready`
- `deadline_date < now`
- Уведомление отправляется раз в сутки (флаг `overdue_notified_date`)

**Получатель:** менеджер

**Текст:**
```
🚨 Заказ просрочен

Заказ: {order.name}
Изделие: {order.item_type_id.name}
Клиент: {order.partner_id.name}
Дедлайн был: {order.deadline_date}
```

---

### 5.4. Заказ перешёл в Ready

**Триггер:** `action_mark_ready`

**Получатель:** пользователи группы `group_jewelry_repair_manager`

**Текст:**
```
✅ Заказ готов к приёмке

Заказ: {order.name}
Изделие: {order.item_type_id.name}
Клиент: {order.partner_id.name}
```

---

### 5.5. Заказ готов к выдаче клиенту

**Триггер:** `action_accept_ready_item` (менеджер принял изделие)

**Получатель:** пользователи группы `group_jewelry_repair_receptionist`

**Текст:**
```
📦 Заказ готов к выдаче

Заказ: {order.name}
Изделие: {order.item_type_id.name}
Клиент: {order.partner_id.name}
```

---

## 6. Технический сервис отправки

### 6.1. Класс `TelegramService`

Утилитный класс (не модель Odoo), реализует отправку через Telegram Bot API:

```
POST https://api.telegram.org/bot{token}/sendMessage
{
  "chat_id": "<chat_id>",
  "text": "<text>",
  "parse_mode": "HTML"
}
```

Библиотеки: только `urllib` (встроенная в Python), без внешних зависимостей.

### 6.2. Правила отправки

- Ошибка отправки (недоступен Telegram, неверный chat_id) **не должна** блокировать бизнес-операцию
- Ошибки логируются через `_logger.warning()`
- Если `bot_token` не задан — отправка пропускается без ошибки
- Если `telegram_chat_id` пользователя не задан — пользователь пропускается

---

## 7. Поля на заказе (для cron-уведомлений)

На `jewelry.repair.order` добавляются технические поля:

| Поле | Тип | Назначение |
|------|-----|-----------|
| `deadline_notified` | Boolean | Флаг: уведомление о дедлайне уже отправлено |
| `overdue_notified_date` | Date | Дата последней отправки о просрочке |

Флаги сбрасываются при изменении `deadline_date`.

---

## 8. Cron

Одна задача: **Check Deadlines and Overdue Orders**

- Модель: `jewelry.repair.order`
- Метод: `_cron_check_deadlines()`
- Расписание: каждый час
- Действия:
  1. Найти заказы с приближающимся дедлайном → отправить, выставить `deadline_notified`
  2. Найти просроченные заказы → отправить (не чаще раз в сутки)

---

## 9. Структура модуля

```
jewelry_telegram_notify/
  __init__.py
  __manifest__.py
  models/
    __init__.py
    res_config_settings.py     # токен, флаги, порог часов
    res_users.py               # telegram_chat_id
    telegram_service.py        # HTTP-сервис отправки
    jewelry_repair_order.py    # _inherit order: флаги + cron + хуки событий
    jewelry_repair_operation.py # _inherit operation: хук назначения
  views/
    res_config_settings_views.xml
    res_users_views.xml
  data/
    ir_cron.xml
  security/
    ir.model.access.csv
  i18n/
    ru.po
```

---

## 10. Критерии приёмки

- [ ] Токен бота сохраняется в настройках, кнопка Test работает
- [ ] `telegram_chat_id` вводится в карточке пользователя
- [ ] При активации операции мастер получает уведомление в Telegram
- [ ] Cron за 24ч до дедлайна отправляет уведомление мастеру и менеджеру
- [ ] Повторное уведомление о том же дедлайне не отправляется
- [ ] Просроченный заказ уведомляет менеджера не чаще раз в сутки
- [ ] При переходе в Ready уведомляются все менеджеры с заданным chat_id
- [ ] При переходе в ready_for_delivery уведомляются приёмщики с заданным chat_id
- [ ] Ошибка Telegram не ломает бизнес-операцию
- [ ] Каждый тип уведомлений отключается отдельной галочкой в настройках
- [ ] Флаги дедлайна сбрасываются при изменении даты дедлайна
