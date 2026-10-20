def migrate(cr, version):
    """Recompute board_priority for all existing order operations."""
    cr.execute("""
        UPDATE jewelry_repair_order_operation
        SET board_priority = CASE state
            WHEN 'in_progress' THEN 10
            WHEN 'ready'       THEN 20
            WHEN 'accepted'    THEN 30
            WHEN 'pending'     THEN 90
            WHEN 'done'        THEN 100
            WHEN 'cancel'      THEN 110
            ELSE 999
        END
        WHERE board_priority IS NULL
           OR board_priority != CASE state
            WHEN 'in_progress' THEN 10
            WHEN 'ready'       THEN 20
            WHEN 'accepted'    THEN 30
            WHEN 'pending'     THEN 90
            WHEN 'done'        THEN 100
            WHEN 'cancel'      THEN 110
            ELSE 999
        END
    """)
