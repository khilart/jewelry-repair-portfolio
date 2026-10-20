#!/usr/bin/env bash
#
# run_tests.sh — clean-install + test run for the jewelry modules.
#
# Spins up a throwaway database, installs every jewelry module from scratch
# (with no demo data) and runs the jewelry test suites. This catches BOTH
# classes of regression we care about:
#   1. clean-install bugs (the modules must install into an empty DB), and
#   2. logic regressions (the unit/integration tests must pass).
#
# Requires the docker-compose stack to be running:  docker compose up -d
#
# Usage:
#   ./scripts/run_tests.sh [db_name]      # default db: jewelry_ci
#
# Exit code 0 = all green, non-zero = install failed or a test failed.
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB="${1:-jewelry_ci}"

# All installable jewelry modules — installing all of them exercises clean install.
MODULES="jewelry_repair_base,jewelry_metal_accounting,jewelry_repair_delivery,jewelry_repair_billing,jewelry_client_metal_accounts,jewelry_repair_portal,jewelry_client_metal_portal,jewelry_telegram_notify,jewelry_3d_library,jewelry_repair_label,jewelry_stone_orders,jewelry_expenses,jewelry_admin_tools"

# Only run our own tests (skip the standard Odoo http test cases, which need a
# live server and fail under --stop-after-init).
TEST_TAGS="/jewelry_repair_base,/jewelry_metal_accounting,/jewelry_repair_delivery,/jewelry_repair_billing,/jewelry_client_metal_accounts,/jewelry_repair_label,/jewelry_stone_orders"

if ! docker compose ps --status running --services 2>/dev/null | grep -qx web; then
  echo "ERROR: the 'web' container is not running. Start it with:  docker compose up -d" >&2
  exit 2
fi

drop_db() {
  docker compose exec -T db psql -U odoo -d postgres \
    -c "DROP DATABASE IF EXISTS $DB;" >/dev/null 2>&1 || true
}

echo "==> Recreating throwaway database '$DB'"
drop_db

echo "==> Installing all modules + running tests (this takes ~30s)"
LOG="$(mktemp)"
docker compose exec -T web odoo \
  -d "$DB" \
  --without-demo=all \
  -i "$MODULES" \
  --test-enable \
  --test-tags "$TEST_TAGS" \
  --stop-after-init 2>&1 | tee "$LOG"
ODOO_RC=${PIPESTATUS[0]}

echo "==> Dropping throwaway database '$DB'"
drop_db

echo
echo "========================================================"

# A registry/install failure never reaches the test summary line.
if grep -qE "Failed to (initialize|load) (database|registry)" "$LOG"; then
  echo "RESULT: FAIL — clean install broke (see log above)"
  rm -f "$LOG"
  exit 1
fi

# Aggregate test result line(s): "odoo.tests.result: A failed, B error(s) of C tests"
RESULT_LINES="$(grep -E "tests\.result:" "$LOG" || true)"
rm -f "$LOG"

if [ -z "$RESULT_LINES" ]; then
  echo "RESULT: FAIL — no tests ran (install problem or wrong test tags)"
  exit 1
fi

echo "$RESULT_LINES" | sed 's/.*tests\.result: /  /'

# Fail if any result line reports something other than "0 failed, 0 error(s)".
if echo "$RESULT_LINES" | grep -qvE "0 failed, 0 error"; then
  echo "RESULT: FAIL"
  exit 1
fi

echo "RESULT: PASS — clean install OK, all tests green"
exit 0
