from odoo import fields


SEED_PREFIX = "[DEMO]"
PASSWORD = "repair123"


def with_seed_prefix(text):
    return f"{SEED_PREFIX} {text}"


def upsert_user(env, *, login, name, group_xmlids):
    user_model = env["res.users"].sudo().with_context(no_reset_password=True)
    group_ids = [env.ref(xmlid).id for xmlid in group_xmlids]
    user = user_model.search([("login", "=", login)], limit=1)
    vals = {
        "name": name,
        "login": login,
        "email": f"{login}@demo.local",
        "password": PASSWORD,
        "groups_id": [(6, 0, group_ids)],
        "active": True,
    }
    if user:
        user.write(vals)
    else:
        user = user_model.create(vals)
    return user


def upsert_executor(env, *, name, sequence, user):
    model = env["jewelry.repair.executor"].sudo()
    record = model.search([("user_id", "=", user.id)], limit=1)
    vals = {
        "name": name,
        "sequence": sequence,
        "user_id": user.id,
        "active": True,
    }
    if record:
        record.write(vals)
    else:
        record = model.create(vals)
    return record


def upsert_item_type(env, name):
    model = env["jewelry.repair.item.type"].sudo()
    record = model.search([("name", "=", name)], limit=1)
    if not record:
        record = model.create({"name": name})
    return record


def upsert_partner(env, name):
    model = env["res.partner"].sudo()
    partner = model.search([("name", "=", name), ("is_company", "=", True)], limit=1)
    vals = {
        "name": name,
        "is_company": True,
        "company_type": "company",
        "customer_rank": 1,
    }
    if partner:
        partner.write(vals)
    else:
        partner = model.create(vals)
    return partner


def upsert_operation(env, *, name, sequence, duration_value, duration_unit, default_executor=False):
    model = env["jewelry.repair.operation"].sudo()
    record = model.search([("name", "=", name)], limit=1)
    vals = {
        "name": name,
        "sequence": sequence,
        "duration_value": duration_value,
        "duration_unit": duration_unit,
        "default_executor_id": default_executor.id if default_executor else False,
        "default_user_id": default_executor.user_id.id if default_executor and default_executor.user_id else False,
        "active": True,
    }
    if record:
        record.write(vals)
    else:
        record = model.create(vals)
    return record


def upsert_service_product(env, *, name, price, operation=False):
    tmpl_model = env["product.template"].sudo()
    tmpl = tmpl_model.search([("name", "=", name)], limit=1)
    vals = {
        "name": name,
        "detailed_type": "service",
        "list_price": price,
        "sale_ok": True,
        "purchase_ok": False,
        "repair_service_ok": True,
        "repair_operation_id": operation.id if operation else False,
    }
    if tmpl:
        tmpl.write(vals)
    else:
        tmpl = tmpl_model.create(vals)
    return tmpl.product_variant_id


def clear_existing_seed_docs(env):
    order_model = env["jewelry.repair.order"].sudo().with_context(active_test=False)
    delivery_model = env["jewelry.repair.delivery"].sudo()
    billing_model = env["jewelry.repair.billing.batch"].sudo()

    seed_orders = order_model.search([("description", "ilike", SEED_PREFIX)])
    seed_deliveries = delivery_model.search([("notes", "ilike", SEED_PREFIX)])
    seed_batches = billing_model.search([("notes", "ilike", SEED_PREFIX)])

    for batch in seed_batches:
        if batch.state == "done":
            batch.order_ids.write({"billing_batch_id": False, "billing_date": False})
        batch.unlink()

    for delivery in seed_deliveries:
        if delivery.state == "done":
            delivery.order_ids.write({"delivery_id": False, "delivery_date": False, "state": "ready"})
        delivery.unlink()

    if seed_orders:
        seed_orders.write(
            {
                "billing_batch_id": False,
                "billing_date": False,
                "delivery_id": False,
                "delivery_date": False,
                "state": "draft",
            }
        )
        seed_orders.unlink()


def create_order(
    env,
    *,
    partner,
    item_type,
    description,
    deadline,
    services,
    notes="",
    quantity=1,
    received_at=None,
):
    order = env["jewelry.repair.order"].sudo().create(
        {
            "partner_id": partner.id,
            "item_type_id": item_type.id,
            "quantity": quantity,
            "received_date": received_at or fields.Datetime.now(),
            "deadline_date": deadline,
            "description": with_seed_prefix(description),
            "notes": with_seed_prefix(notes) if notes else False,
        }
    )
    for sequence, service in enumerate(services, start=1):
        env["jewelry.repair.service.line"].sudo().create(
            {
                "order_id": order.id,
                "sequence": sequence * 10,
                "product_id": service["product"].id,
                "name": service.get("name") or service["product"].display_name,
                "operation_id": service.get("operation_id", service["product"].product_tmpl_id.repair_operation_id.id),
                "quantity": service["quantity"],
                "price_unit": service.get("price_unit", service["product"].lst_price),
            }
        )
    return order


def assign_operations(order, assignments):
    by_name = {operation.operation_id.name: operation for operation in order.order_operation_ids}
    users = order.env["res.users"].sudo()
    for operation_name, payload in assignments.items():
        operation = by_name[operation_name]
        user = users.search([("login", "=", payload["login"])], limit=1)
        vals = {"assigned_user_id": user.id}
        if payload.get("state"):
            vals["state"] = payload["state"]
        if payload.get("started_at"):
            vals["started_at"] = payload["started_at"]
        if payload.get("done_at"):
            vals["done_at"] = payload["done_at"]
        if payload.get("notes"):
            vals["notes"] = with_seed_prefix(payload["notes"])
        operation.write(vals)


def create_demo_users_and_executors(env):
    receptionist = upsert_user(
        env,
        login="demo.reception",
        name="Анна Приемка",
        group_xmlids=[
            "base.group_user",
            "jewelry_repair_base.group_jewelry_repair_receptionist",
        ],
    )
    stone_master = upsert_user(
        env,
        login="demo.master.stones",
        name="Игорь Закрепщик",
        group_xmlids=[
            "base.group_user",
            "jewelry_repair_base.group_jewelry_repair_master",
        ],
    )
    polish_master = upsert_user(
        env,
        login="demo.master.polish",
        name="Марина Полировщик",
        group_xmlids=[
            "base.group_user",
            "jewelry_repair_base.group_jewelry_repair_master",
        ],
    )
    manager = upsert_user(
        env,
        login="demo.manager",
        name="Олег Руководитель",
        group_xmlids=[
            "base.group_user",
            "jewelry_repair_base.group_jewelry_repair_manager",
        ],
    )

    executors = {
        "reception": upsert_executor(env, name="Анна Приемка", sequence=10, user=receptionist),
        "stones": upsert_executor(env, name="Игорь Закрепщик", sequence=20, user=stone_master),
        "polish": upsert_executor(env, name="Марина Полировщик", sequence=30, user=polish_master),
        "manager": upsert_executor(env, name="Олег Руководитель", sequence=40, user=manager),
    }
    return {
        "users": {
            "reception": receptionist,
            "stones": stone_master,
            "polish": polish_master,
            "manager": manager,
        },
        "executors": executors,
    }


def mark_all_operations_done(order):
    for operation in order.order_operation_ids:
        if operation.operation_id.default_user_id:
            operation.write({"assigned_user_id": operation.operation_id.default_user_id.id})
        acting_user = operation.assigned_user_id or operation.operation_id.default_user_id or order.env.user
        if operation.state == "ready":
            operation.with_user(acting_user).action_accept_item()
        if operation.state in ("accepted", "in_progress"):
            operation.with_user(acting_user).action_mark_done()
        elif operation.state == "pending":
            operation.action_set_ready()
            operation.with_user(acting_user).action_accept_item()
            operation.with_user(acting_user).action_mark_done()


def accept_ready_by_manager(order, manager_user):
    if order.state == "ready" and not order.ready_accepted_by_manager:
        order.with_user(manager_user).action_accept_ready_item()


def main(env):
    clear_existing_seed_docs(env)
    demo_people = create_demo_users_and_executors(env)
    users = demo_people["users"]
    executors = demo_people["executors"]

    ring = upsert_item_type(env, "Кольцо")
    earrings = upsert_item_type(env, "Серьги")
    pendant = upsert_item_type(env, "Подвеска")
    bracelet = upsert_item_type(env, "Браслет")

    client_a = upsert_partner(env, "Ювелирный дом Аврора")
    client_b = upsert_partner(env, "Салон украшений Гранат")
    client_c = upsert_partner(env, "Бутик Серебряная линия")

    op_diagnostics = upsert_operation(
        env, name="Диагностика", sequence=10, duration_value=15, duration_unit="minutes", default_executor=executors["manager"]
    )
    op_resize = upsert_operation(
        env, name="Изменение размера", sequence=20, duration_value=2, duration_unit="hours", default_executor=executors["stones"]
    )
    op_solder = upsert_operation(
        env, name="Пайка", sequence=30, duration_value=45, duration_unit="minutes", default_executor=executors["stones"]
    )
    op_stones = upsert_operation(
        env, name="Закрепка камней", sequence=40, duration_value=30, duration_unit="minutes", default_executor=executors["stones"]
    )
    op_polish = upsert_operation(
        env, name="Полировка", sequence=50, duration_value=2, duration_unit="hours", default_executor=executors["polish"]
    )
    op_quality = upsert_operation(
        env, name="Финишный контроль", sequence=60, duration_value=20, duration_unit="minutes", default_executor=executors["manager"]
    )

    svc_diagnostics = upsert_service_product(env, name="Диагностика изделия", price=15.0, operation=False)
    svc_resize = upsert_service_product(env, name="Изменение размера кольца", price=45.0, operation=op_resize)
    svc_solder = upsert_service_product(env, name="Пайка элемента", price=35.0, operation=op_solder)
    svc_stones = upsert_service_product(env, name="Закрепка мелких камней", price=55.0, operation=op_stones)
    svc_polish = upsert_service_product(env, name="Полировка изделия", price=25.0, operation=op_polish)
    svc_quality = upsert_service_product(env, name="Финишный контроль", price=10.0, operation=op_quality)

    today = fields.Date.today()
    now = fields.Datetime.now()

    order_reception = create_order(
        env,
        partner=client_a,
        item_type=ring,
        description="Кольцо с деформацией шинки и потертостями",
        deadline=today,
        services=[
            {"product": svc_diagnostics, "quantity": 1},
            {"product": svc_resize, "quantity": 1},
            {"product": svc_polish, "quantity": 1},
        ],
        notes="Заказ только что принят на стойке. Нужно оценить объем работ и подготовить к запуску.",
        received_at=now,
    )

    order_waiting_master = create_order(
        env,
        partner=client_b,
        item_type=earrings,
        description="Серьги с ослабленной закрепкой центральных камней",
        deadline=today,
        services=[
            {"product": svc_stones, "quantity": 2},
            {"product": svc_polish, "quantity": 1},
        ],
        notes="Клиент просил проверить обе серьги и не менять внешний вид оправы.",
        received_at=now,
    )
    order_waiting_master.action_generate_operations()
    order_waiting_master.action_start()
    assign_operations(
        order_waiting_master,
        {
            "Закрепка камней": {
                "login": "demo.master.stones",
                "state": "ready",
                "notes": "Сначала проверить левую серьгу, затем правую.",
            },
            "Полировка": {
                "login": "demo.master.polish",
                "state": "pending",
            },
        },
    )
    order_waiting_master._sync_operation_flow()

    order_in_progress = create_order(
        env,
        partner=client_b,
        item_type=ring,
        description="Кольцо с восстановлением посадки камней и последующей полировкой",
        deadline=today,
        services=[
            {"product": svc_stones, "quantity": 1},
            {"product": svc_polish, "quantity": 1},
        ],
        notes="Основная задача для экрана мастера. После закрепки передать в полировку без возврата на приемку.",
        received_at=now,
    )
    order_in_progress.action_generate_operations()
    order_in_progress.action_start()
    assign_operations(
        order_in_progress,
        {
            "Закрепка камней": {
                "login": "demo.master.stones",
                "state": "accepted",
                "notes": "Проверить посадку камня под увеличением перед началом работы.",
            },
            "Полировка": {
                "login": "demo.master.polish",
                "state": "pending",
            },
        },
    )
    order_in_progress._sync_operation_flow()

    order_ready = create_order(
        env,
        partner=client_c,
        item_type=bracelet,
        description="Браслет после пайки и полировки, готов к выдаче",
        deadline=today,
        services=[
            {"product": svc_solder, "quantity": 1},
            {"product": svc_polish, "quantity": 1},
            {"product": svc_quality, "quantity": 1},
        ],
        notes="Заказ используется для проверки выдачи и статуса ready.",
        received_at=now,
    )
    order_ready.action_generate_operations()
    order_ready.action_start()
    mark_all_operations_done(order_ready)

    order_delivered = create_order(
        env,
        partner=client_c,
        item_type=pendant,
        description="Подвеска после ремонта ушка, уже выдана клиенту",
        deadline=today,
        services=[
            {"product": svc_solder, "quantity": 1},
            {"product": svc_polish, "quantity": 1},
        ],
        notes="Демонстрационный заказ в статусе delivered.",
        received_at=now,
    )
    order_delivered.action_generate_operations()
    order_delivered.action_start()
    mark_all_operations_done(order_delivered)
    accept_ready_by_manager(order_delivered, users["manager"])

    delivery = env["jewelry.repair.delivery"].sudo().create(
        {
            "partner_id": client_c.id,
            "delivery_date": today,
            "order_ids": [(6, 0, [order_delivered.id])],
            "notes": with_seed_prefix("Выдача демонстрационного заказа"),
        }
    )
    delivery.action_confirm()

    order_billed = create_order(
        env,
        partner=client_a,
        item_type=ring,
        description="Кольцо, уже включенное в биллинг за период",
        deadline=today,
        services=[
            {"product": svc_resize, "quantity": 1},
            {"product": svc_polish, "quantity": 1},
        ],
        notes="Демонстрационный заказ для проверки billing batch.",
        received_at=now,
    )
    order_billed.action_generate_operations()
    order_billed.action_start()
    mark_all_operations_done(order_billed)
    accept_ready_by_manager(order_billed, users["manager"])

    billed_delivery = env["jewelry.repair.delivery"].sudo().create(
        {
            "partner_id": client_a.id,
            "delivery_date": today,
            "order_ids": [(6, 0, [order_billed.id])],
            "notes": with_seed_prefix("Выдача заказа, который попадет в биллинг"),
        }
    )
    billed_delivery.action_confirm()

    batch = env["jewelry.repair.billing.batch"].sudo().create(
        {
            "partner_id": client_a.id,
            "date_from": today,
            "date_to": today,
            "order_ids": [(6, 0, [order_billed.id])],
            "notes": with_seed_prefix("Демонстрационный billing batch"),
        }
    )
    batch.action_confirm()

    env.cr.commit()
    print("demo seed complete")
    print("demo users:")
    print("  demo.reception / repair123")
    print("  demo.master.stones / repair123")
    print("  demo.master.polish / repair123")
    print("  demo.manager / repair123")
    print(f"reception_order:{order_reception.name}")
    print(f"waiting_master_order:{order_waiting_master.name}")
    print(f"in_progress_order:{order_in_progress.name}")
    print(f"ready_order:{order_ready.name}")
    print(f"delivered_order:{order_delivered.name}")
    print(f"billed_order:{order_billed.name}")


main(env)
