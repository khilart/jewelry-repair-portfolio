def migrate(cr, version):
    """Backfill the purity snapshot and fine weights on existing metal moves.

    Historical moves have no purity of their own, so the only value available is
    the alloy's current purity. Moves that already carry a snapshot are left alone.
    """
    cr.execute("""
        UPDATE jewelry_metal_move m
        SET purity = a.purity,
            fine_in = m.weight_in * a.purity,
            fine_out = m.weight_out * a.purity,
            fine_signed = (m.weight_in - m.weight_out) * a.purity
        FROM jewelry_metal_alloy a
        WHERE a.id = m.alloy_id
          AND (m.purity IS NULL OR m.purity = 0)
    """)
