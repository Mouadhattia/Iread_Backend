# Applying the billing migration without shell access

For FTP/phpMyAdmin deployments where `flask db upgrade` cannot be run on the
server. These files are the exact SQL that `flask db upgrade` would execute,
generated with `flask db upgrade <from>:<to> --sql`.

## 1. Find out where the production database actually is

In phpMyAdmin, on the production database, run:

```sql
SELECT version_num FROM alembic_version;
```

## 2. Pick the matching file

| `version_num` says | Run this file |
|---|---|
| `b8e3c1a7f2d9` | `billing-migration-from-b8e3c1a7f2d9.sql` |
| `e5f8c1a2d740` | `billing-migration-from-e5f8c1a2d740.sql` |
| `c9a2e5f81b34` | Already up to date — the 500 has a different cause |
| anything else | Stop and ask; the right script has to be generated for that revision |

If the `alembic_version` table does not exist at all, stop — the database was
not built by migrations and needs looking at before applying anything.

## 3. Before running it

**Take a backup first**, from phpMyAdmin's Export tab (or mysqldump). Save it
somewhere **outside** the repository folder — a dump committed to git is how
real user data ends up on GitHub.

## 4. Run it

Paste the file's contents into phpMyAdmin's SQL tab, or use its Import tab.
Each script ends with the `UPDATE alembic_version ...` line that records the
new revision — do not remove it, or the next migration will try to re-apply
this one.

## If it fails with "Table 'admin_audit_logs' already exists"

That table was created outside migrations. Check it is empty:

```sql
SELECT COUNT(*) FROM admin_audit_logs;
```

If it is empty, drop it and re-run. If it has rows, keep it and instead run
only `billing-migration-from-b8e3c1a7f2d9.sql`, after setting:

```sql
UPDATE alembic_version SET version_num = 'b8e3c1a7f2d9';
```

## 5. Verify

```sql
SHOW TABLES LIKE 'school\_%';      -- expect school_billing_profile,
                                   -- school_invoice, school_seat_activation,
                                   -- school_subscription (+ existing school_* tables)
SELECT code, total_cents FROM contract_plan;   -- expect starter/growth/scale
SELECT version_num FROM alembic_version;       -- expect c9a2e5f81b34
```

## 6. Backfill the seat ledger

`scripts/backfill_seat_activations.py` needs Python on the server. If you
cannot run it, seat counts start at zero and only count students activated
from that point on — existing readers will not appear until the script is run.
Ask before working around this; the correct fix is to run the script once.
