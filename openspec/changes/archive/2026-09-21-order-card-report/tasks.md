# Tasks: Order Card

## 1. Отчёт в jewelry_repair_base

- [x] 1.1 `reports/order_card_report.xml`: action + QWeb-шаблон, подключить в манифест
- [x] 1.2 Шапка, основные поля, фото, веса
- [x] 1.3 Таблицы услуг, материалов в счёт, камней с номером сертификата
- [x] 1.4 Итоги: «Full product cost», «To pay»
- [x] 1.5 Переводы в `i18n/ru.po`

## 2. Зачёт металла в jewelry_client_metal_accounts

- [x] 2.1 Наследование шаблона: «Order amount», «Paid with metal», «To pay» после зачёта
- [x] 2.2 Переводы в `i18n/ru.po`

## 3. Проверка

- [x] 3.1 Обновить модули на `testWork`, сгенерировать PDF для заказа с камнями и сертификатом,
      с материалами, с партией, с зачётом металла
- [x] 3.2 Влить дельту в `openspec/specs/repair/print/spec.md`, запись в `DECISIONS.md`
