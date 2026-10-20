from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Seed base_price from the price actually sold, so historical margin reads as zero."""
    cr.execute("""
        UPDATE jewelry_repair_service_line
        SET base_price = price_unit
        WHERE base_price IS NULL OR base_price = 0
    """)
    # base_amount and margin were computed while base_price was still empty, which read the
    # whole revenue as the manager's markup.
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["jewelry.repair.service.line"].search([])
    for field in ("base_amount", "margin"):
        env.add_to_compute(lines._fields[field], lines)
        lines.flush_recordset([field])
