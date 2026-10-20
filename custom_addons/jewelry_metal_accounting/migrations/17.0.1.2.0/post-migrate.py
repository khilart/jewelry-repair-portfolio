def migrate(cr, version):
    """Drop the running_balance column left behind by the removed field.

    Odoo removes the ir.model.fields record when a field disappears from the
    model but keeps the database column, so it has to be dropped explicitly.
    """
    cr.execute("ALTER TABLE jewelry_metal_move DROP COLUMN IF EXISTS running_balance")
