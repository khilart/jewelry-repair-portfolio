def post_init_hook(env):
    """Create the predefined expense accounts after the chart of accounts is loaded.

    On an existing database (the production case) the chart already exists, so the
    accounts are created here. On a combined clean install the chart loads last and
    would purge them — the Expenses view re-creates them lazily via
    ``_ensure_expense_accounts`` on first open.
    """
    env["jewelry.expense.entry"]._ensure_expense_accounts()
