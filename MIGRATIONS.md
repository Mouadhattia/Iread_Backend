# "Can't locate revision identified by ..."

## The symptom

The deploy job fails at the migration step:

```
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
ERROR [flask_migrate] Error: Can't locate revision identified by 'eafac216fc6e'
Error: Process completed with exit code 1.
```

and `GET /admin/super/system/migrations` returns 500 with the same text.

Both come from the same cause, which is why they appear together.

## What it actually means

The `alembic_version` table holds one row: the revision the database believes
it is at. In this state that row names a revision that exists in **no file**
under `migrations/versions/`.

Alembic works by walking a graph of migrations. If it cannot find the node the
database claims to be standing on, it cannot compute a path to the head — so it
refuses to upgrade, and it cannot even answer "what is pending". That second
part is why the status page 500s rather than showing a warning.

**The schema is almost always fine.** It is the bookmark that is wrong, not the
tables. Nothing is corrupted and no data is lost.

## How a database gets into this state

The common one, and the one that produced this incident: a database was dropped
and re-created from a dump, and that dump was taken from a server whose
`migrations/versions/` folder held a file this repository does not.

That happens most easily when `flask db migrate` is run **directly on the
server**. It writes a new version file into the server's `migrations/versions/`
and applies it, so the database records that revision. The deploy workflow then
rsyncs the repository over the server with `--delete`, which removes the
generated file — because it was never committed — while the row it wrote stays
in the database for ever.

The other route is a migration that was applied somewhere and later deleted or
rewritten in git.

> Never run `flask db migrate` on the server. Generate migrations locally and
> commit them. The deploy only ever runs `flask db upgrade`.

## Fixing it

From a shell on the server, in the backend folder, with the venv active.

### 1. Back up first

```bash
mysqldump -u USER -p DBNAME > ~/iread-before-repair.sql
```

Save it **outside** the repository folder. A dump committed to git is how real
user data ends up on GitHub.

### 2. Diagnose

```bash
python scripts/repair_alembic_version.py
```

This changes nothing. It reads the live schema and checks, one revision at a
time along the migration chain, whether that revision's tables and columns are
genuinely present — so the answer is derived from the database, not guessed:

```
Migration pointer
  alembic_version says : eafac216fc6e
  code head            : e2c8b4d1f036
  pointer resolves     : NO

Schema probe
  [ yes ] a335f2c4499a   table user
  ...
  [ yes ] c9a2e5f81b34   table contract_plan
  [ NO  ] d1b4f7c3a982   column shcool.trial_seats
  [ NO  ] e2c8b4d1f036   table school_file
  newest revision fully present : c9a2e5f81b34
  first revision not applied    : d1b4f7c3a982

BROKEN: the database points at 'eafac216fc6e', which exists in no migration file.
Would set alembic_version to c9a2e5f81b34.
`flask db upgrade` would then apply 2 migration(s): d1b4f7c3a982, e2c8b4d1f036
```

Read the probe table before doing anything else. It should be a solid run of
`yes` followed by a solid run of `NO`. If the script reports
`applied out of order`, stop — that means schema was changed outside migrations
and stamping would skip a migration that is genuinely needed.

### 3. Repair, then upgrade

```bash
python scripts/repair_alembic_version.py --apply
flask db upgrade
```

`--apply` only rewrites the one row in `alembic_version`. It never touches a
table. `flask db upgrade` then applies whatever is genuinely missing.

### 4. Confirm

```bash
flask db current    # should print the head revision
```

or reload the super-admin **System → Database** page, which should read
"Up to date".

## Overriding the detection

If you know the detection is wrong — for instance the orphaned revision did
something the probe cannot see:

```bash
python scripts/repair_alembic_version.py --to <revision> --apply
```

The script refuses any revision that is not in `migrations/versions/`, so it
cannot be used to recreate the same problem.

## What the code does about it now

* `scripts/repair_alembic_version.py` — the diagnostic and repair tool above.
* `apps/system_migrations.py` — checks the revision resolves before walking the
  graph. The status payload gained `unknown_revision` and `diagnosis`, so the
  endpoint returns 200 with an explanation rather than 500. `run_upgrade()`
  raises `UnknownRevision` instead of letting alembic fail obscurely, which the
  API returns as 409 `UNKNOWN_REVISION`.
* Super-admin **System → Database** page — renders the diagnosis and the repair
  commands, and disables the upgrade button, which cannot help here.
* `.github/workflows/deploy.yml` — when `flask db upgrade` fails it runs
  `repair_alembic_version.py --check`, so the job log says which of the two
  failures it was. It deliberately does **not** repair anything on its own:
  rewriting database state is not something a push should do unattended.

## If the alembic_version table is missing entirely

The script reports this separately. It means the database was not built by
migrations at all.

* If the schema is empty, just run `flask db upgrade`.
* If the schema has tables, run the diagnostic, check the probe output, and
  stamp with `--to <revision> --apply` — do not guess.
