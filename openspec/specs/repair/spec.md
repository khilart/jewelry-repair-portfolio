# Repair — Заказы ремонта

## Purpose

Центральный контур системы. Управляет жизненным циклом заказа ремонта от приёмки изделия до выдачи клиенту. Включает каталоги услуг, материалов, операций, исполнителей, а также учёт металлопотерь по зонам.

Модуль: `jewelry_repair_base`

## Критичные разделения (не смешивать)

```
Услуга (service.line)  ≠  Операция (order.operation)
  коммерческая              производственная

draft → in_progress → ready → delivered (статусы заказа)

ready (все операции done)  ≠  delivered (выдан клиенту)  ≠  billing (попал в счёт)

executor_id (плановый исполнитель)  ≠  assigned_user_id (фактически назначенный)

Материалы клиента (информационно)  ≠  Материалы мастерской (склад + в счёт)
```

## Ключевые модели

### jewelry.repair.order — Заказ ремонта

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Номер заказа (авто, из последовательности) |
| partner_id | Many2one (res.partner) | Клиент (только те, у кого customer_rank > 0) |
| item_type_id | Many2one (jewelry.repair.item.type) | Тип изделия (кольцо, браслет, и т.д.) |
| item_size_id | Many2one (jewelry.repair.item.size) | Размер изделия |
| quantity | Integer | Количество изделий в партии |
| alloy_id | Many2one (jewelry.metal.alloy) | Сплав |
| metal_id | Many2one (jewelry.metal) | Металл (вычислен из сплава) |
| received_weight | Float | Вес при приёмке (г) |
| delivered_weight | Float | Вес при выдаче (г) |
| metal_delivered_weight | Float | Вес металла без камней (delivered_weight − gem_weight_total_g) |
| fine_weight_received | Float | Вес лигатуры принятого (received_weight × purity) |
| fine_weight_delivered | Float | Вес лигатуры выданного (delivered_weight × purity) |
| weight_delta | Float | Разница delivered − received |
| gem_weight_total_g | Float | Суммарный вес камней в граммах |
| received_with_gems_g | Float | received_weight + gem_weight_total_g |
| state | Selection | draft / in_progress / ready / delivered / cancel |
| received_date | Datetime | Дата приёмки |
| deadline_date | Datetime | Срок выдачи |
| metal_rate_at | Datetime | Дата котировки металла для материальных строк |
| earliest_ready_date | Datetime | Расчётная ранняя дата готовности (по длительности операций) |
| deadline_warning | Char | Предупреждение, если дедлайн раньше earliest_ready_date |
| amount_total | Monetary | Сумма заказа (услуги + материалы в счёт + камни в счёт) |
| total_duration_minutes | Float | Суммарное расчётное время работы (мин) |
| total_duration_display | Char | Читаемое отображение времени (Xd Xh Xm) |
| new_product_manufacturing | Boolean | Признак: изготовление нового изделия (не ремонт) |
| item_image | Image | Фото изделия |
| description | Text | Описание изделия и работы |
| external_doc_number | Char | Внешний номер документа |
| notes | Text | Внутренние заметки |
| current_holder_user_id | Many2one (res.users) | Текущий держатель изделия |
| current_holder_role | Selection | Роль держателя: receptionist/master/manager/customer |
| current_location_type | Selection | reception / in_work / ready_for_delivery / delivered |
| last_move_at | Datetime | Время последней передачи |
| ready_accepted_by_manager | Boolean | Принято менеджером перед выдачей |
| ready_accepted_at | Datetime | Время приёмки менеджером |
| certificate_numbers | Char | Сводный список номеров сертификатов камней |
| service_line_ids | One2many | Строки услуг |
| material_line_ids | One2many | Строки материалов |
| gem_line_ids | One2many | Строки камней |
| order_operation_ids | One2many | Производственные операции заказа |
| area_loss_ids | One2many | Потери металла по зонам |
| total_metal_loss_percent | Float | Суммарный % потери металла по зонам |
| weight_tracking_enabled | Boolean | Включён ли учёт веса для данного заказа |

### jewelry.repair.item.type — Тип изделия

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название (кольцо, браслет и т.д.) |
| active | Boolean | Активен |
| size_ids | One2many | Доступные размеры |

### jewelry.repair.item.size — Размер изделия

| Поле | Тип | Описание |
|------|-----|----------|
| item_type_id | Many2one | Тип изделия |
| size_eu | Float | EU размер |
| size_ru | Float | RU размер (диаметр мм) |
| name | Char | Отображение «EU / RU» (вычислено) |
| sequence | Integer | Порядок сортировки |

### jewelry.repair.service.line — Строка услуги

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one | Заказ |
| product_id | Many2one (product.product) | Продукт-услуга (repair_service_ok=True) |
| name | Char | Описание (по умолчанию — название продукта на en_US) |
| operation_id | Many2one (jewelry.repair.operation) | Тип производственной операции |
| quantity | Float | Кол-во на изделие |
| batch_quantity | Integer | Количество изделий в партии |
| total_quantity | Float | quantity × batch_quantity |
| price_unit | Float | Цена за единицу |
| subtotal | Float | total_quantity × price_unit |
| sequence | Integer | Порядок в таблице |

### jewelry.repair.material.line — Строка материала

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one | Заказ |
| order_operation_id | Many2one | Операция заказа (к которой привязан материал) |
| product_id | Many2one (product.product) | Материал/деталь (repair_material_ok=True) |
| quantity | Float | Количество |
| uom_id | Many2one | Единица измерения |
| weight | Float | Вес (г) |
| weight_loss | Float | Возвратные потери (weight × return_loss_percent / 100) |
| alloy_id | Many2one (jewelry.metal.alloy) | Сплав |
| rate_datetime | Datetime | Дата котировки металла |
| rate_price_per_gram | Monetary | Котировка: цена за грамм чистого металла |
| price_unit | Monetary | Цена за единицу (auto из котировки × purity × (weight + weight_loss)) |
| subtotal | Monetary | quantity × price_unit |
| subtotal_editable | Boolean | Только менеджер может редактировать сумму напрямую |
| include_in_invoice | Boolean | Включить в счёт клиенту |
| consume_from_stock | Boolean | Списать со склада |
| source_storage_id | Many2one | Склад списания (для consume_from_stock) |
| return_to_storage | Boolean | Вернуть на склад |
| return_storage_id | Many2one | Склад возврата |
| is_auto_calculated | Boolean | Создана автоматически (металлорасчётом) |
| description | Text | Описание |

### jewelry.repair.operation — Шаблон операции (справочник)

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название |
| sequence | Integer | Порядок в маршруте |
| area_id | Many2one (jewelry.work.area) | Производственная зона |
| is_gem_setting | Boolean | Операция закрепки (влияет на расчёт потерь) |
| duration_value | Float | Расчётная длительность |
| duration_unit | Selection | minutes / hours / days |
| duration_days | Float | Длительность в рабочих днях (8ч = 1 день) |
| duration_minutes | Float | Длительность в минутах |
| default_executor_id | Many2one (jewelry.repair.executor) | Исполнитель по умолчанию |
| default_user_id | Many2one (res.users) | Пользователь по умолчанию |
| loss_recoverable_percent | Float | % возвратных потерь металла |
| loss_irrecoverable_percent | Float | % безвозвратных потерь металла |
| active | Boolean | Активна |

### jewelry.repair.order.operation — Операция заказа (производственная)

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one | Заказ |
| operation_id | Many2one (jewelry.repair.operation) | Тип операции |
| executor_id | Many2one (jewelry.repair.executor) | Плановый исполнитель |
| assigned_user_id | Many2one (res.users) | Назначен на пользователя |
| state | Selection | pending / ready / accepted / in_progress / done / cancel |
| planned_date | Date | Плановая дата |
| planned_scope | Selection | overdue / today / tomorrow / future / no_date |
| board_priority | Integer | Приоритет для сортировки на доске |
| weight_before | Float | Вес изделия перед операцией (г) |
| metal_was_added | Boolean | Металл был добавлен в этой операции |
| accepted_by_user_id | Many2one | Кто принял изделие |
| accepted_at | Datetime | Время принятия |
| started_at | Datetime | Время начала |
| done_at | Datetime | Время завершения |
| estimated_duration_minutes | Float | Расчётная длительность из строк услуг |
| estimated_duration_display | Char | Читаемое отображение |
| notes | Text | Заметки исполнителя |
| service_line_ids | Many2many | Строки услуг, породившие операцию |
| material_line_ids | One2many | Материалы, использованные в операции |
| next_order_operation_id | Many2one | Следующая операция |
| next_executor_id | Many2one | Исполнитель следующей |
| next_assigned_user_id | Many2one | Назначен на следующую |
| prev_order_operation_id | Many2one | Предыдущая операция |
| sequence | Integer | Порядок в маршруте |

### jewelry.repair.executor — Исполнитель

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Имя |
| sequence | Integer | Порядок колонок на доске планирования |
| user_id | Many2one (res.users) | Связанный пользователь (уникален) |
| manager_user_ids | Many2many | Менеджеры (зарезервировано) |
| active | Boolean | Активен |

### jewelry.work.area — Производственная зона

| Поле | Тип | Описание |
|------|-----|----------|
| name | Char | Название |
| sequence | Integer | Порядок сортировки |
| is_casting | Boolean | Зона литья (вес_in = материалы, не weight_before) |

### jewelry.order.area.loss — Потери металла по зоне

| Поле | Тип | Описание |
|------|-----|----------|
| order_id | Many2one | Заказ |
| area_id | Many2one (jewelry.work.area) | Зона |
| weight_in | Float | Вес на входе зоны (г) |
| weight_out | Float | Вес на выходе зоны (г) |
| loss | Float | Потеря = weight_in − weight_out |
| loss_percent | Float | Потеря % |

### jewelry.order.client.loss — Потери металла по клиенту (SQL View)

Вид, показывающий потери металла по каждому выданному заказу: клиент, тип изделия, received_weight, metal_delivered_weight, loss, loss_percent.

### jewelry.repair.client.price — Индивидуальные цены клиента

| Поле | Тип | Описание |
|------|-----|----------|
| partner_id | Many2one | Клиент |
| product_id | Many2one | Услуга |
| base_price | Float | Базовая цена продукта (из прайса) |
| discount_percent | Float | Скидка/наценка % (положительный = скидка) |
| custom_price | Float | Фиксированная цена (перебивает базу + скидку) |
| final_price | Float | Итоговая цена (вычислена) |

### jewelry.repair.kpi.dashboard — Финансовый дашборд (Transient)

Дашборд отображает: ожидающие заказы, в работе, готовые к выдаче; выручку текущего и прошлого месяца (раздельно услуги и материалы); полученные платежи; разбивку по услугам, материалам, клиентам.

### product.template (расширение)

| Поле | Тип | Описание |
|------|-----|----------|
| repair_service_ok | Boolean | Доступен как услуга ремонта |
| repair_material_ok | Boolean | Доступен как материал ремонта |
| repair_material_requires_weight | Boolean | Вес обязателен при использовании |
| repair_material_default_invoice | Boolean | По умолчанию включать в счёт |
| repair_material_default_consume | Boolean | По умолчанию списывать со склада |
| repair_material_return_loss_percent | Float | % возвратных потерь (по умолчанию 10%) |
| repair_material_nonreturn_loss_percent | Float | % безвозвратных потерь (по умолчанию 3%) |
| repair_operation_id | Many2one | Операция по умолчанию для услуги |
| gem_pricing_type | Selection | fixed / per_carat — тип расчёта цены для камней |

## Requirements

### Requirement: Жизненный цикл заказа

Заказ проходит статусы: `draft → in_progress → ready → delivered`. Возможен переход в `cancel` из любого состояния (кроме delivered).

#### Scenario: Запуск заказа в работу

- GIVEN заказ в статусе `draft`
- WHEN приёмщик нажимает "Start"
- THEN система генерирует производственные операции из услуг (если операций нет)
- AND операции группируются по типу операции, сортируются по `sequence`
- AND заказ переходит в `in_progress`
- AND вес принятого изделия автоматически проставляется в `weight_before` первой операции
- AND если вес не заполнен и пользователь не менеджер — показывается ошибка; менеджеру — предупреждение
- AND для нового изделия (new_product_manufacturing=True) вес не обязателен

#### Scenario: Автоматический переход в ready

- GIVEN заказ `in_progress`, все операции выполнены (state=done)
- WHEN последняя операция помечается Done
- THEN заказ автоматически переходит в `ready`
- AND пересчитываются потери металла по зонам (area_loss_ids)

#### Scenario: Принудительное завершение менеджером

- GIVEN заказ `in_progress`, есть незавершённые операции
- WHEN менеджер нажимает "Mark Ready"
- THEN открывается диалог с количеством незавершённых операций
- WHEN менеджер подтверждает
- THEN все незавершённые операции помечаются как done
- AND заказ переходит в `ready`

#### Scenario: Приёмка менеджером перед выдачей

- GIVEN заказ в статусе `ready`
- WHEN менеджер нажимает "Accept Ready Item"
- THEN проверяются: вес выданного изделия, металлодокументы (создаются автоматически если не созданы)
- AND заполняются ready_accepted_by_manager=True, ready_accepted_at
- AND текущий держатель = менеджер, location = ready_for_delivery
- AND если вес не заполнен — показывается предупреждение (не блокирует)

#### Scenario: Отмена и возврат в черновик

- GIVEN заказ в любом статусе кроме delivered
- WHEN нажимается Cancel или Reset to Draft
- THEN металлодокументы отменяются и удаляются
- AND потери по зонам (area_loss_ids) очищаются
- AND операции возвращаются в pending

---

### Requirement: Производственные операции

Операции создаются из строк услуг, одна операция на тип (несколько услуг одного типа — в одну операцию). Маршрут: только первая незавершённая операция имеет статус `ready`, остальные — `pending`.

#### Scenario: Принятие изделия мастером

- GIVEN операция в статусе `ready`, назначена мастеру
- WHEN мастер нажимает "Accept Item"
- THEN если вес tracking включён: открывается диалог ввода веса перед операцией
- THEN если вес tracking выключен или режим входа — менеджер: принятие без диалога
- AND операция переходит в `accepted`
- AND текущий держатель = мастер, location = in_work

#### Scenario: Выполнение операции

- GIVEN операция в статусе `accepted`
- WHEN мастер нажимает "Start"
- THEN операция переходит в `in_progress`, фиксируется started_at

#### Scenario: Завершение операции

- GIVEN операция в статусе `accepted` или `in_progress`
- WHEN мастер нажимает "Done"
- THEN операция переходит в `done`, фиксируется done_at
- AND следующая операция переходит в `ready`
- AND если следующая операция назначена тому же мастеру — автоматически принимается (accepted)

#### Scenario: Возврат на переделку

- GIVEN операция в статусе `done`, заказ не выдан
- WHEN мастер (или менеджер) нажимает "Return to Rework"
- THEN операция возвращается в `ready` (если назначена) или `pending`
- AND заказ возвращается в `in_progress`
- AND флаги ready_accepted_by_manager очищаются

#### Scenario: Назначение на себя

- GIVEN операция без assigned_user_id
- WHEN пользователь нажимает "Assign To Me"
- THEN assigned_user_id = текущий пользователь, executor_id = соответствующий исполнитель

---

### Requirement: Строки услуг

Каждый заказ содержит коммерческие строки услуг. Цена подставляется из индивидуального прайса клиента (если есть) или из базовой цены продукта.

#### Scenario: Автоматическая цена из прайса клиента

- GIVEN услуга добавляется в заказ
- WHEN пользователь выбирает продукт
- THEN проверяется наличие individual price для данного клиента и продукта
- AND если есть — используется final_price, иначе — lst_price

#### Scenario: Количество в партии

- GIVEN заказ с quantity > 1
- WHEN добавляется услуга
- THEN batch_quantity = quantity заказа
- AND total_quantity = qty_per_item × batch_quantity
- AND subtotal = total_quantity × price_unit

---

### Requirement: Строки материалов и металлорасчёт

Материалы могут автоматически рассчитывать цену по текущей котировке металла.

#### Scenario: Автоматическая цена металла

- GIVEN материальная строка с заполненным alloy_id и weight
- WHEN изменяется alloy_id, weight или rate_datetime
- THEN ищется котировка металла (jewelry.metal.rate) на указанную дату
- AND price_unit = rate_price_per_gram × purity × (weight + weight_loss) / quantity
- AND если котировка не найдена — цена = 0 и не дастся сохранить строку

#### Scenario: Применение единой даты котировки

- GIVEN заказ с material_line_ids
- WHEN менеджер изменяет metal_rate_at и нажимает кнопку обновления
- THEN открывается диалог с количеством строк
- WHEN подтверждает
- THEN rate_datetime всех строк (у которых не зафиксирована собственная дата) = metal_rate_at заказа

#### Scenario: Синхронизация металлодокументов

- GIVEN заказ в статусе `ready`, менеджер нажимает "Sync Metal Documents"
- THEN создаётся (или перезаписывается) металлодокумент типа Write-Off и Receipt
- AND строки с consume_from_stock=True → write-off из source_storage
- AND строки с return_to_storage=True → receipt в return_storage
- AND если у строки нет source_storage_id — ошибка
- AND если строка consume_from_stock=True без include_in_invoice и без return_to_storage — предупреждение

---

### Requirement: Камни (Stones)

Камни добавляются во вкладке "Stones" заказа. Поддерживаются сертификаты GIA/IGI/HRD и других лабораторий.

#### Scenario: Добавление камня из фото сертификата

- GIVEN на заказе открыта вкладка Stones
- WHEN пользователь нажимает "Add from Certificate" и загружает фото
- THEN через Claude API (claude-sonnet-4-6) распознаётся информация с сертификата
- AND создаётся запись jewelry.gem.certificate (или предлагается использовать существующую с тем же номером)
- AND строка камня заполняется данными из сертификата

#### Scenario: Генерация услуг закрепки

- GIVEN заказ со строками камней
- WHEN пользователь нажимает "Generate Setting Services"
- THEN для каждого камня ищется подходящее правило (setting_rule) по типу камня и весу
- AND создаются строки услуг с продуктом из правила
- AND ценообразование: fixed → одна строка на правило; per_carat → строка на каждую строку камня

---

### Requirement: Учёт металлопотерь по зонам

Автоматически рассчитывается при переходе заказа в `ready` и при изменении delivered_weight в статусах ready/delivered.

#### Scenario: Расчёт потерь

- GIVEN заказ `ready`, выполненные операции с weight_before > 0
- THEN операции группируются по производственной зоне (area_id)
- AND weight_in зоны = weight_before первой операции зоны (с поправками на камни и материалы)
- AND weight_out зоны = weight_before первой операции следующей зоны (или delivered_weight для последней)
- AND вес камней вычитается из weight_out/weight_in зоны закрепки и всех последующих
- AND материалы-добавки (consume_from_stock, не литьё) вычитаются из последующих зон
- AND материалы на возврат (return_to_storage) прибавляются к последующим зонам
- AND для зоны литья (is_casting) weight_in = сумма потреблённых материалов кастинга

---

### Requirement: Расчётный срок выполнения

#### Scenario: Предупреждение о дедлайне

- GIVEN услуги с duration_minutes заполнены
- WHEN рассчитывается earliest_ready_date (от received_date + суммарные минуты с учётом рабочих часов 9-13, 14-18)
- AND deadline_date < earliest_ready_date
- THEN поле deadline_warning показывает предупреждение с расчётной датой

---

### Requirement: Планирование (Planned Operations)

Канбан-доска планирования позволяет назначать операции исполнителям.

#### Scenario: Назначение через канбан

- GIVEN менеджер переносит карточку операции в колонку другого исполнителя
- WHEN карточка перемещается
- THEN executor_id = выбранный исполнитель, assigned_user_id = executor.user_id

#### Scenario: Auto Assign

- GIVEN операции без assigned_user_id
- WHEN нажимается "Auto Assign Operations"
- THEN для каждой незаполненной операции ищется default_executor_id из шаблона операции
- AND если найден — заполняются executor_id и assigned_user_id
- AND операции с уже назначенным исполнителем не затрагиваются

---

### Requirement: Роли и доступ

| Роль | Что делает |
|------|-----------|
| Мастер (Master) | Видит только "My Work" — свои операции. Принимает/запускает/завершает операции. |
| Приёмщик (Receptionist) | Создаёт заказы, вводит услуги и материалы |
| Менеджер (Manager) | Все права + принятие готовых изделий, принудительное завершение, Metal Documents |
| Управляет любой операцией (Manages Any Operation) | Может действовать от лица любого назначенного; видит предупреждения вместо ошибок при пустом весе |
| Директор (Director) | Только чтение — write() заблокирован |

#### Scenario: Мастер видит только свои операции

- GIVEN пользователь с ролью Мастер
- WHEN он открывает систему
- THEN он видит только приложение "My Work" с личными операциями
- AND главное меню "Jewelry Repair" скрыто

---

### Requirement: Настройки веса

В Settings → Jewelry Repair задаётся:
- **Weight Tracking Mode**: disabled / new_product_only / all — управляет включением учёта веса и расчётом потерь по зонам
- **Weight Entry By**: master (диалог при Accept Item) / manager (ввод напрямую в таблицу операций)

---

## UI-контракты (не менять без явного указания)

- В канбане `Work Operations` поле `Planning Date` находится в верхней панели строго между строкой поиска и кнопками выбора вида
- Порядок колонок в `Planned Operations` определяется `sequence` у `Operation Executor`
- Главное меню: `Orders`, `Planned Operations`, `Deliveries` — быстрые пункты; `Payments` — раздел для delivery + billing + invoicing
- Форма операции мастера отображает: дедлайн, фото изделия, тип/сплав/размер, заметки заказа, услуги, следующий шаг, материалы
- На канбан-карточке: цветная полоска сверху по статусу (синяя=in_progress, жёлтая=accepted, зелёная=ready, серая=остальные)
- В форме заказа кнопка "Sync Metal Documents" видна только менеджеру и администратору и только в статусе ready
- Кнопка "Accept Ready Item" видна только менеджеру, только в статусе ready и если ещё не принято

## Ссылки

Исторические ТЗ: отсутствуют (центральный модуль, нет отдельного ТЗ в корне)
