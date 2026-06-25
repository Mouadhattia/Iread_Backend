# IRead Backend Project Structure

Generated from a local scan on 2026-06-05.

This document maps the current Flask backend and highlights the places that matter for the planned multi-school update. In the current code, "school" is usually spelled `shcool`; this document keeps that spelling when referring to existing files, models, routes, and database columns.

## High-Level Shape

The backend is a Flask application using SQLAlchemy, Flask-Login, Flask-Mail, Flask-Migrate/Alembic, MySQL, GeoIP, external quiz/invoicing APIs, and some NLP/Neo4j helper scripts.

Main entry point:

- `app.py` creates the Flask app, applies `ConfigClass`, initializes `mail`, `login_manager`, `db`, `Migrate`, enables CORS, and registers the four blueprints.
- `/reader` handles reader authentication, account flows, reader dashboard, profiles, pack/session following, quizzes, and game results.
- `/admin` handles administration for users, roles, sessions, books, packs, codes, analytics, schools, templates, notifications, and NLP helpers.
- `/main` handles public/shared book, session, pack, and contact email endpoints.
- `/teacher` currently exposes a small teacher dashboard endpoint.

## Repository Tree

```text
Iread_Backend/
|-- app.py
|-- config.py
|-- extensions.py
|-- readme.md
|-- requirements.txt
|-- .gitignore
|-- LICENSE
|-- Doxyfile
|-- quiz.json
|-- test.json
|-- iread_backup.sql
|-- backup-01-05-2025.sql
|-- apps/
|   |-- __init__.py
|   |-- admin/
|   |   |-- routes.py
|   |   |-- paserStory.py
|   |   |-- graphDBscripts/
|   |   |   |-- db.py
|   |   |   |-- parserDataset.py
|   |   |   |-- create_cefr_db.log
|   |-- main/
|   |   |-- routes.py
|   |   |-- email.py
|   |-- reader/
|   |   |-- routes.py
|   |-- teacher/
|   |   |-- routes.py
|-- models/
|   |-- about_book.py
|   |-- book.py
|   |-- book_pack.py
|   |-- book_text.py
|   |-- chat.py
|   |-- code.py
|   |-- Follow_book.py
|   |-- follow_pack.py
|   |-- follow_session.py
|   |-- game_result.py
|   |-- notification_user.py
|   |-- pack.py
|   |-- pack_template.py
|   |-- profile.py
|   |-- session.py
|   |-- session_quiz.py
|   |-- shcool.py
|   |-- teacher_postulate.py
|   |-- unit.py
|   |-- user.py
|   |-- user_log.py
|   |-- user_shcool.py
|-- migrations/
|   |-- alembic.ini
|   |-- env.py
|   |-- README
|   |-- script.py.mako
|   |-- versions/
|   |   |-- 29ca84dad37b_completed.py
|   |   |-- 634199115db3_.py
|   |   |-- bba77237ecbe_initial_migrati.py
|   |   |-- cca2296b8c96_date.py
|-- versions/
|   |-- a335f2c4499a_first.py
|   |-- 4aeb195624eb_.py
|-- templates/
|   |-- admin_email_template.html
|   |-- confirmation_email_template.html
|   |-- customer_email_template.html
|   |-- intellect_admin_email_template.html
|   |-- intellect_customer_email_template.html
|-- docs/
|   |-- Generated Doxygen HTML, CSS, JS, images, and search assets
|-- GeoLite2-City/
|   |-- GeoLite2-City.mmdb
|   |-- README.txt
|   |-- LICENSE.txt
|   |-- COPYRIGHT.txt
|-- project-structure/
|   |-- project-structure.md
|-- venv/
|-- __pycache__/
```

Note: `venv/`, `__pycache__/`, generated Doxygen internals, and binary database data are not expanded in detail.

## Runtime And Configuration

| File | Role |
| --- | --- |
| `app.py` | Flask app factory-style module, CORS setup, OAuth object, extension initialization, blueprint registration, root health response. |
| `config.py` | MySQL connection, mail settings, frontend/API URLs, quiz/invoicing keys, session lifetime. |
| `extensions.py` | Shared `Mail`, `LoginManager`, and `SQLAlchemy` instances. |
| `requirements.txt` | Python dependencies: Flask stack, SQLAlchemy/Alembic, MySQL drivers, requests, GeoIP, SpaCy, NLTK, Neo4j, etc. |
| `readme.md` | Setup/run guide. Current selected run command: `flask run --debug --port 3001`. |

## Blueprints And Route Areas

| Blueprint | Prefix | File | Current responsibility |
| --- | --- | --- | --- |
| `reader` | `/reader` | `apps/reader/routes.py` | Registration, login, Google login, multi-account selection, profile, pack/session enrollment, teacher application, quiz integration, games, game results, school pack listing. |
| `admin` | `/admin` | `apps/admin/routes.py` | User and role admin, reader/teacher/assistant listings, sessions, books, units, packs, follow approvals, codes, logs, dashboard analytics, school CRUD, templates, book text, about-book data, notifications, NLP helpers. |
| `main` | `/main` | `apps/main/routes.py` | Public/shared book-session search, session/pack details, pack listing, pack books, email/contact endpoints. |
| `teacher` | `/teacher` | `apps/teacher/routes.py` | Teacher dashboard guarded by teacher role. |

The route modules are currently large and mostly procedural. `apps/admin/routes.py` has the largest surface by far and should be split before or during the multi-school work if the update becomes broad.

## Model Inventory

| Model | File | Current purpose | School scope today |
| --- | --- | --- | --- |
| `User` | `models/user.py` | Base polymorphic user table with username, email, password hash, confirmation, approval, image, role type, quiz ID. | No direct `school_id`; connected through `User_shcool`. |
| `Reader` | `models/user.py` | Reader subtype with level and invoicing client ID. | Indirect through `User_shcool`. |
| `Teacher` | `models/user.py` | Teacher subtype with description, study level, availability. | Indirect through `User_shcool`. |
| `Admin` | `models/user.py` | Admin subtype with invoicing API user ID. | Indirect through `User_shcool`. |
| `Assistant` | `models/user.py` | Assistant subtype with invoicing API user ID. | Indirect through `User_shcool`. |
| `Shcool` | `models/shcool.py` | School master table with `id` and `name`. | Root school entity. |
| `User_shcool` | `models/user_shcool.py` | Many-to-many join between users and schools. | Direct school membership table. |
| `Pack` | `models/pack.py` | Pack/course product with title, level, age, price, discount, FAQ, invoicing product ID, duration, public flag. | Direct `shcool_id` FK. |
| `Pack_template` | `models/pack_template.py` | Reusable pack template storing book-pack IDs in JSON. | No direct school FK; imported into a school pack using current user's school. |
| `Book` | `models/book.py` | Global book catalog with title, author, image, description, release date, pages, category, Neo4j ID. | No direct school FK. |
| `Book_pack` | `models/book_pack.py` | Many-to-many join between packs and books. | Inherits scope through `Pack`. |
| `Book_text` | `models/book_text.py` | Text content for a book. Table name is `bok_text`. | No direct school FK. |
| `About_Book` | `models/about_book.py` | JSON metadata/about data for books. | No direct school FK. |
| `Unit` | `models/unit.py` | Unit/chapter attached to a book. | No direct school FK. |
| `Session` | `models/session.py` | Scheduled session/class with book, unit, teacher, pack, dates, price, location, active flag, meet link. | No direct school FK; can be derived through `pack_id -> Pack.shcool_id`. |
| `Session_quiz` | `models/session_quiz.py` | Quiz token attached to a session. | No direct school FK; can be derived through session. |
| `Follow_pack` | `models/follow_pack.py` | User follows/enrolls in a pack, with approval state. | No direct school FK; can be derived through pack. |
| `Follow_session` | `models/follow_session.py` | User follows/enrolls in a session, with approval/presence. | No direct school FK; can be derived through session. |
| `Follow_book` | `models/Follow_book.py` | User follows/progresses a book inside a pack/unit. | No direct school FK; can be derived through pack. |
| `Code` | `models/code.py` | Access/enrollment code for a pack, with status and optional user. | No direct school FK; can be derived through pack. |
| `Game_result` | `models/game_result.py` | Per-user game score/progress for a book and day. | No school, pack, or session FK; needs explicit scoping decision. |
| `Notification_user` | `models/notification_user.py` | Notification ID attached to user. | No direct school FK; can be derived through user membership if needed. |
| `Profile` | `models/profile.py` | User profile/contact fields. | No direct school FK; tied to user. |
| `UserLog` | `models/user_log.py` | Visitor/user-agent/country/city/browser/system/cookie log. | No direct school FK; currently global analytics. |
| `Teacher_postulate` | `models/teacher_postulate.py` | Reader application to become a teacher. | No direct school FK; can be derived through applicant's school. |
| `Chat` | `models/chat.py` | Session chat message. | No direct school FK; can be derived through session. |

## Current School-Related Code

Existing school support:

- `models/shcool.py` defines `Shcool`.
- `models/user_shcool.py` links users to schools.
- `models/pack.py` stores `Pack.shcool_id`.
- Reader registration, Google registration, and account creation attach new readers to the hard-coded school named `IRead`.
- `reader/user_authenticated` returns a single `school_id`/`school` for admins and a list of schools for non-admin users.
- `reader/get_packs_by_school` filters packs by `school` query parameter and `public` flag for unauthenticated users.
- Admin reader/teacher/assistant listings filter users through the current admin's first `User_shcool`.
- Admin create user/assistant/teacher attaches new accounts to the current admin's first school.
- Admin pack creation accepts `school_id` from the request body and stores it in `Pack.shcool_id`.
- Admin pack import from template creates a pack under the current user's school.
- Admin follow request listing filters requests by pack school.
- Admin has CRUD routes for `Shcool`: create, list, update, delete, get one.

Current gaps for true multi-school isolation:

- Many admin routes are global or partly global: books, units, sessions, analytics, logs, notifications, codes, quiz/session operations, and some follow actions.
- Many admin auth decorators are commented out, so route-level access control is inconsistent.
- Several flows trust client-provided IDs, including `school_id`, `pack_id`, `session_id`, and `user_id`, without always checking they belong to the current school.
- `Session` has no direct `school_id`; it depends on `Pack.shcool_id`. This is workable, but every session query must join or validate through pack.
- `Game_result` has only `user_id` and `book_id`; it cannot distinguish the same book used by different schools/packs.
- `UserLog` and dashboard analytics are global.
- `Book`, `Unit`, `Book_text`, and `About_Book` are global catalog/content tables. That may be correct, but the decision should be explicit.

## Current Data Flow

Startup:

1. `app.py` creates the Flask app.
2. `ConfigClass` loads database, mail, API, and session settings.
3. `mail`, `login_manager`, and `db` are initialized.
4. Flask-Migrate is attached.
5. `reader`, `teacher`, `admin`, and `main` blueprints are registered.

Authentication:

1. Reader registration/login lives in `apps/reader/routes.py`.
2. `User`, `Reader`, `Teacher`, `Admin`, and `Assistant` are polymorphic SQLAlchemy models.
3. Flask-Login loads users from `User.query.get(int(user_id))`.
4. New reader accounts are currently linked to hard-coded school `IRead`.

Admin/user management:

1. Admin routes use `current_user.type == 'admin'` in `admin_required`.
2. Some admin routes are guarded, but many guard decorators are commented out.
3. Current school context is usually found by `User_shcool.query.filter_by(user_id=current_user.id).first()`.
4. New users created by an admin are linked to the admin's first school.

Pack/session flow:

1. Admin creates a `Pack` with `shcool_id`.
2. Admin adds books to the pack through `Book_pack`.
3. Admin creates `Session` records using `book_id`, `unit_id`, `teacher_id`, and `pack_id`.
4. Readers follow packs with `Follow_pack`, sessions with `Follow_session`, and books with `Follow_book`.
5. Codes are generated per pack and can activate/follow a pack.

Quiz/game flow:

1. Quizzes are pulled/assigned through external quiz API endpoints.
2. `Session_quiz` links a quiz token to a session.
3. Game results are stored in `Game_result` by user, book, game, day, and completion.

## Multi-School Backend Checklist

Recommended target behavior:

- Every admin dashboard and admin data flow should resolve an active school context before querying.
- School admins should only see and mutate users, packs, sessions, follows, codes, notifications, analytics, and quiz assignments that belong to their school.
- Super admins, if needed, should have an explicit global role or permission, not accidental access through unfiltered routes.
- Reader flows should use the reader's selected/active school, not a hard-coded `IRead` school.
- Public pack browsing should filter by school, public visibility, or both.

Suggested implementation order:

1. Add school context helpers:
   - `get_current_school_id()`
   - `require_school_admin()`
   - `query_school_packs()`
   - `assert_pack_in_school(pack_id, school_id)`
   - `assert_session_in_school(session_id, school_id)`
2. Normalize naming in Python while preserving existing DB compatibility:
   - Keep table/column migrations careful because the current DB uses `shcool`.
   - Consider adding `School = Shcool` or renaming model code first, then migrating table/column names later.
3. Decide which data is global versus school-owned:
   - Likely global: book catalog, book text, about-book data, units, pack templates.
   - Likely school-owned: users, roles, packs, sessions, follows, codes, notifications, quiz assignments, game results, logs, analytics.
4. Add or derive school scope consistently:
   - `Pack` already has `shcool_id`.
   - `Session` can derive school from pack, but direct `school_id` may simplify filtering and indexing.
   - `Game_result` probably needs `pack_id`, `session_id`, or `school_id`.
   - `Notification_user` and `UserLog` need a school-scope decision.
5. Update all list/detail/update/delete routes to enforce school checks before returning or mutating data.
6. Backfill existing data:
   - Create/confirm default school `IRead`.
   - Attach existing users to that school.
   - Backfill all packs to that school where `shcool_id` is missing.
   - Backfill derived session/game/log scope if adding new columns.
7. Add indexes and constraints:
   - `user_shcool(shcool_id, user_id)`
   - `pack(shcool_id, title)` if pack titles should only be unique inside a school.
   - `session(pack_id)`, and maybe `session(school_id, start_date)` if adding direct school ID.
   - `follow_pack(pack_id, user_id)`, `follow_session(session_id, user_id)`.
8. Add tests for isolation:
   - Admin from school A cannot list/update/delete school B users.
   - Admin from school A cannot mutate school B packs, sessions, follows, codes, or quiz assignments.
   - Reader cannot join a private pack from another school using only an ID or code.
   - Dashboard analytics are school-filtered.

## Watch Items Before Refactor

- `config.py` contains database, email, quiz, and invoicing secrets in source. Move them to environment variables and rotate exposed credentials.
- `.gitignore` ignores `migrations/`, but `migrations/` exists in the repo. Decide whether migrations should be tracked consistently.
- There are migration files both in root `versions/` and `migrations/versions/`.
- Many admin routes have `@login_required` and `@admin_required` commented out.
- `Book` defines `img` twice.
- `Book` imports `Shcool`, and admin serialization references `book.shcool_id`, but the current `Book` model does not define `shcool_id`.
- `Book_text` uses table name `bok_text`.
- `User_shcool.__repr__` references `self.pack_id`, which does not exist.
- `Session.__repr__` and `Session_quiz.__repr__` reference `self.date`, which does not exist.
- Admin route `@admin.route('update_code/<int:code_id>', methods=['PUT'])` is missing a leading slash.
- Several routes use broad `except Exception` handlers, which can hide school isolation bugs during the refactor.

## Practical Next Step

For the multi-school update, start by building a small school-context layer and applying it to `apps/admin/routes.py` pack/session/user flows first. Those are the highest-risk areas because they control dashboard visibility and data mutation. After that, apply the same school checks to reader enrollment, codes, game results, and analytics.
