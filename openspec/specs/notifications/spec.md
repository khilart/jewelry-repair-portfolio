# Notifications — Telegram-уведомления

## Purpose

Push-уведомления в Telegram о событиях жизненного цикла заказов ремонта. Уведомляет мастеров о новых задачах, менеджеров о готовности заказов и дедлайнах. Поддерживает утренний дайджест и напоминания о бездействии.

Модуль: `jewelry_telegram_notify`

Историческое ТЗ: `TELEGRAM_NOTIFY_SPEC.md`

## Ключевые модели

### res.users (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| telegram_chat_id | Char | Telegram Chat ID пользователя |
| inactivity_notified_at | Datetime | Последнее время уведомления о бездействии |

### jewelry.repair.order (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| deadline_notified | Boolean | Уведомление о приближении дедлайна уже отправлено |
| overdue_notified_date | Date | Дата последнего уведомления о просрочке |
| morning_digest_sent_date | Date | Дата отправки утреннего дайджеста |

### jewelry.repair.order.operation (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| assign_notify_pending | Boolean | Уведомление об операции отложено до рабочих часов |

## Настройки (Settings → Jewelry Repair → Telegram)

| Параметр | Описание |
|----------|----------|
| Bot Token | Токен Telegram-бота |
| Timezone | Часовой пояс для форматирования дат (по умолчанию Europe/Brussels) |
| Notify: operation assigned | Мастеру при назначении операции |
| Notify: morning digest | Утренний дайджест дедлайнов |
| Notify: deadline approaching | За 1.5 часа до дедлайна |
| Notify: order overdue | При просрочке заказа |
| Notify: order ready | При переходе в ready (менеджерам) |
| Notify: order delivery ready | При принятии готового изделия менеджером (приёмщикам) |
| Notify: master inactivity | Напоминание при бездействии мастера |
| Inactivity threshold hours | Порог бездействия (часов, по умолчанию 1) |
| Working hours start/end | Рабочие часы (по умолчанию 10-18) |
| Working days | Флаги Mon-Sun (по умолчанию Mon-Fri) |
| Test Chat ID | Chat ID для тестирования уведомлений |

## Requirements

### Requirement: Уведомление о назначении операции

#### Scenario: Немедленное уведомление в рабочее время

- GIVEN операция назначена мастеру с telegram_chat_id
- WHEN назначение происходит в рабочие часы
- THEN мастер немедленно получает сообщение: "Новая задача: заказ, изделие, операция, клиент, дедлайн, ссылка на My Work"

#### Scenario: Отложенное уведомление вне рабочего времени

- GIVEN операция назначена вне рабочих часов
- THEN assign_notify_pending=True на операции
- AND следующим утром (cron morning digest) уведомление отправляется автоматически

#### Scenario: Уведомление при активации операции

- GIVEN операция assigned_user_id уже заполнен, операция переходит из pending → ready
- THEN та же логика — немедленно или отложено

---

### Requirement: Утренний дайджест

Запускается по cron.

#### Scenario: Дайджест для мастера

- GIVEN cron срабатывает утром в рабочий день
- THEN ищутся заказы с deadline_date = сегодня, в статусах in_progress/ready/accepted
- AND для каждого мастера, у которого есть активные операции по этим заказам с telegram_chat_id
- THEN отправляется сообщение со списком заказов: номер, тип, клиент, время дедлайна

#### Scenario: Дайджест для менеджера

- THEN менеджерам с telegram_chat_id отправляется полный список дедлайнов на сегодня с назначенными мастерами

#### Scenario: Флаг отправки

- WHEN дайджест отправлен
- THEN morning_digest_sent_date = сегодня на заказах (повторная отправка сегодня не происходит)

---

### Requirement: Уведомления о дедлайнах

Запускается по cron в рабочие часы.

#### Scenario: Предупреждение за 1.5 часа до дедлайна

- GIVEN заказ в статусе draft/in_progress, deadline_date ∈ (now, now+1.5h], deadline_notified=False
- THEN мастерам активных операций и всем менеджерам с telegram_chat_id отправляется предупреждение
- AND deadline_notified=True (повторно не отправляется)
- AND при изменении deadline_date флаг сбрасывается

#### Scenario: Просроченные заказы

- GIVEN заказ draft/in_progress с deadline_date < now, overdue_notified_date < сегодня (или не заполнен)
- THEN менеджерам отправляется уведомление о просрочке
- AND overdue_notified_date = сегодня (один раз в день)

---

### Requirement: Уведомление о готовности заказа

#### Scenario: Заказ готов к приёмке (→ ready)

- WHEN заказ переходит в статус `ready`
- THEN менеджерам с telegram_chat_id отправляется: "Заказ готов к приёмке: номер, изделие, клиент"

#### Scenario: Заказ готов к выдаче (Accept Ready Item)

- WHEN менеджер принимает изделие (action_accept_ready_item)
- THEN приёмщикам с telegram_chat_id отправляется: "Заказ готов к выдаче: номер, изделие, клиент"

---

### Requirement: Напоминание о бездействии мастера

Запускается по cron в рабочие часы.

#### Scenario: Мастер не стартовал работу

- GIVEN у мастера есть операции в состоянии ready/accepted
- AND последнее started_at < now − threshold_hours
- AND inactivity_notified_at < now − threshold_hours (или не заполнен)
- THEN мастеру отправляется напоминание со ссылкой на My Work
- AND inactivity_notified_at = now

---

### Requirement: Тестирование уведомлений

В Settings → Telegram есть:
- "Test Connection" — отправляет тестовое сообщение текущему пользователю
- "Test Morning Digest" — запускает _cron_morning_digest на Test Chat ID
- "Test Deadlines" — запускает _cron_check_deadlines на Test Chat ID
- "Test Inactivity" — запускает _cron_check_master_inactivity на Test Chat ID
