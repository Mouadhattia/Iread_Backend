# Multi-School Readiness Audit

Generated from a local scan on 2026-06-05.

Short answer: the backend has the start of multi-school support, but it is not fully ready for safe multi-school operation yet. The schema has `Shcool`, `User_shcool`, and `Pack.shcool_id`, and some list endpoints already use them. The main missing work is route enforcement: many endpoints still expose or mutate global data by raw IDs without checking the current user's school.

Update note: a first backend pass has now added a blueprint-level admin guard and school-context helpers to `apps/admin/routes.py`, then applied school checks to the main admin user, pack, session, follow, code, notification, log, and dashboard routes. The remaining items below should be read as the original audit plus follow-up areas, especially reader/public routes and deeper cleanup.

Update note 2: the backend now has school invitation codes. Admins can generate/list/update/delete invite codes for their own school, readers can redeem an invite code from settings through `/reader/join_school_by_invitation`, and reader/Google signup can optionally include `invitation_code` while keeping the existing default signup behavior.

Update note 3: reader-side direct school discovery/joining is now available through `/reader/get_all_schools` and `/reader/join_school`. The join route accepts either one `school_id` or multiple `school_ids`.

Update note 4: reader followed-pack and dashboard session reads are now school-scoped. `/reader/get_followed_pack_list`, `/reader/get_unfollowed_books`, and `/reader/dashboard` accept `school`, `school_id`, or `shcool_id` and filter through `Pack.shcool_id`.

Update note 5: reader pack detail/books reads are now school-aware through `/reader/get_pack_details` and `/reader/get_books_from_pack`. The legacy `/main/get_pack_details` also now includes `books`/`books_in_pack`.

Update note 6: school admin self-signup is now available through `/reader/register_school_admin` and `/reader/signup_school_admin`. The route creates the school, creates a pending admin user, links them through `user_shcool`, and waits for super-admin approval before that admin can log in.

Update note 7: admin book reads are now school-scoped through `Book_pack -> Pack.shcool_id`. `/admin/show_all_books`, `/admin/get_book/<id>`, `/admin/update_book`, and `/admin/delete_book` no longer expose or mutate books that are not linked to the current admin's school packs.

Update note 8: a `super_admin` role is now available. Super admins can bootstrap through `/reader/register_super_admin` when none exists, authenticate like other users, and use global `/admin/super/dashboard`, `/admin/super/users`, `/admin/super/books`, `/admin/super/packs`, and `/admin/super/schools` routes. Existing school CRUD routes are now restricted to super admins.

Update note 9: super-admin list routes now use backend pagination with `page` and `per_page`. Super admins can filter pending admin accounts through `/admin/super/users?role=admin&approved=false` and approve school admins through `/admin/super/approve_school_admin`.

## What Is Already Ready

- `models/shcool.py` defines the school table.
- `models/user_shcool.py` links users to schools.
- `models/pack.py` has `shcool_id`, so packs can belong to one school.
- `apps/admin/routes.py` filters reader, teacher, and assistant listing by the current admin's school in `/show_all_readers`, `/show_all_teachers`, and `/show_all_assistants`.
- `apps/admin/routes.py` attaches admin-created users/teachers/assistants to the current admin's school.
- `apps/reader/routes.py` returns school data from `/user_authenticated`.
- `apps/reader/routes.py` has `/get_packs_by_school`, which filters packs by `school` query parameter.
- `backup-01-05-2025.sql` includes `shcool`, `user_shcool`, and `pack.shcool_id`.

## Must Update Before Real Multi-School Use

### 1. Admin route guards are mostly disabled

Only 9 of 96 admin routes have active `@login_required` and `@admin_required`. 41 admin routes have login guards commented out and 39 have admin guards commented out.

Examples:

- `apps/admin/routes.py:180` `/show_all_readers`
- `apps/admin/routes.py:351` `/update_user`
- `apps/admin/routes.py:841` `/sessions`
- `apps/admin/routes.py:1678` `/create_pack`
- `apps/admin/routes.py:2023` `/approve_pack_follow_request`
- `apps/admin/routes.py:2521` `/code_in_pack/<pack_id>`
- `apps/admin/routes.py:3015` `/create_shcool`

This is the first thing to fix. School isolation does not help if dashboard/admin routes are public or callable without admin checks.

### 2. Admin list endpoints are partly school-filtered, but detail/update/delete routes are not

Some lists are filtered by `User_shcool`, but related mutation endpoints use only IDs.

Examples:

- `apps/admin/routes.py:319` `/get_user/<user_id>` uses `User.query.get(user_id)` with no school check.
- `apps/admin/routes.py:351` `/update_user` uses `User.query.get(user_id)` with no school check.
- `apps/admin/routes.py:656` `/update_teacher` uses `Teacher.query.get(teacher_id)` with no school check.
- `apps/admin/routes.py:716` `/approved_user` approves any user ID.
- `apps/admin/routes.py:744` `/delete_user` deletes any user ID.

Needed update: before any user read/update/delete/approve, verify the target user belongs to the current admin's school through `User_shcool`.

### 3. Session routes are global

`Session` has no direct school field, so every session route must validate through `Session.pack_id -> Pack.shcool_id`. Right now many routes do not.

Examples:

- `apps/admin/routes.py:841` `/sessions` returns `Session.query.all()`.
- `apps/admin/routes.py:887` `/sessions_by_teacher/<teacher_id>` filters only by teacher.
- `apps/admin/routes.py:910` `/reader_in_session/<session_id>` trusts `session_id`.
- `apps/admin/routes.py:1022` `/sessions_in_book` returns sessions by book only.
- `apps/admin/routes.py:1066` `/create_session` accepts `pack_id`, `teacher_id`, `book_id` without school validation.
- `apps/admin/routes.py:1149` `/delete_session` deletes by session ID.
- `apps/admin/routes.py:1207` `/update_session` updates by session ID.

Needed update: add helpers like `get_current_school_id()` and `assert_session_in_school(session_id, school_id)`.

### 4. Pack mutation routes are not school-safe

`Pack` has `shcool_id`, but several routes trust request IDs.

Examples:

- `apps/admin/routes.py:1678` `/create_pack` accepts `request.json['school_id']`. A school admin can submit another school ID.
- `apps/admin/routes.py:1739` `/add_book_to_pack` loads `Pack` by ID only.
- `apps/admin/routes.py:1780` `/delete_book_from_pack` loads `Pack` by ID only.
- `apps/admin/routes.py:1811` `/delete_pack` deletes by pack ID only.
- `apps/admin/routes.py:1842` `/update_pack_details` updates by pack ID only.

Needed update: school admins should not submit `school_id`; derive it from `current_user`. Every pack operation should query `Pack` by both `id` and current school.

### 5. Follow request approval/deletion can affect another school

The listing endpoints filter by school after loading all rows, but the mutation endpoints do not validate school ownership.

Examples:

- `apps/admin/routes.py:2023` `/approve_pack_follow_request`
- `apps/admin/routes.py:2054` `/reject_pack_follow_request`
- `apps/admin/routes.py:2085` `/delete_follow_request`
- `apps/admin/routes.py:2116` `/create_follow_pack`
- `apps/admin/routes.py:2205` `/create_follow_session`
- `apps/admin/routes.py:2289` `/approve_session_follow_request`
- `apps/admin/routes.py:2319` `/reject_session_follow_request`
- `apps/admin/routes.py:2350` `/delete_session_follow_request`

Needed update: validate pack/session school before approving, rejecting, creating, or deleting follow records.

### 6. Codes are global by ID/code string

Codes are attached to packs, so they can be scoped through `Code.pack_id -> Pack.shcool_id`, but current routes do not enforce it.

Examples:

- `apps/admin/routes.py:2521` `/code_in_pack/<pack_id>`
- `apps/admin/routes.py:2535` `/delete_code/<code_id>`
- `apps/admin/routes.py:2565` `/generate_code_in_pack/<pack_id>`
- `apps/admin/routes.py:2586` `update_code/<code_id>`
- `apps/admin/routes.py:2603` `/get_code/<code_client>`

Needed update: admin code operations must verify the code's pack belongs to the current school.

### 7. Dashboard analytics and logs are global

Examples:

- `apps/admin/routes.py:2623` `/get_all_logs` uses `UserLog.query.all()`.
- `apps/admin/routes.py:2660` `/get_dashboard_analytics` uses `UserLog.query.all()` and `User.query.all()`.

Needed update: filter users through `User_shcool` and logs through those users. Decide what to do with anonymous logs that have no `user_id`.

### 8. Reader registration still hard-codes `IRead`

Examples:

- `apps/reader/routes.py:162` registration attaches new users to school named `IRead`.
- `apps/reader/routes.py:219` Google login attaches new users to `IRead`.
- `apps/reader/routes.py:486` extra account creation attaches users to `IRead`.

Needed update: registration should accept or infer the target school from invite, subdomain, selected school, or admin-created account flow.

### 9. Reader helper/game endpoints accept raw `user_id`

Examples:

- `apps/reader/routes.py:966` `/add_user_to__session` accepts `user_id` and has no active login guard.
- `apps/reader/routes.py:1006` `/remove_user_from_session` accepts `user_id` and has no active login guard.
- `apps/reader/routes.py:1104` `/link_code` accepts `user_id` and code, with no active login guard.
- `apps/reader/routes.py:1756` `/game-result/` accepts `user_id` from JSON.
- `apps/reader/routes.py:1831` `/game-result/<result_id>` updates by result ID.

Needed update: self-service reader endpoints should use `current_user.id`; admin-style endpoints should move under admin routes and check school.

### 10. Public main routes are not school-aware

Examples:

- `apps/main/routes.py:208` `/show_all_pack` returns all public packs from all schools.
- `apps/main/routes.py:253` `/get_pack_details` returns a pack by ID only.
- `apps/main/routes.py:286` `/get_books_from_pack` returns pack books by pack ID only.

This may be acceptable for a global public catalog, but if each school dashboard/site should be separate, these routes need school filtering too.

## Database Backup Warning

- `backup-01-05-2025.sql` has the school schema.
- `iread_backup.sql` does not appear to include `shcool`, `user_shcool`, or `pack.shcool_id`.

Do not restore `iread_backup.sql` as the base for multi-school work unless you add the missing school schema afterward.

## Recommended Next Implementation Step

Start with a small school-context layer before editing every route:

```python
from flask import abort

def get_current_school_id():
    membership = User_shcool.query.filter_by(user_id=current_user.id).first()
    return membership.shcool_id if membership else None

def get_school_pack_or_404(pack_id):
    school_id = get_current_school_id()
    pack = Pack.query.filter_by(id=pack_id, shcool_id=school_id).first()
    if not pack:
        abort(404)
    return pack

def get_school_session_or_404(session_id):
    school_id = get_current_school_id()
    session = (
        db.session.query(Session)
        .join(Pack, Session.pack_id == Pack.id)
        .filter(Session.id == session_id, Pack.shcool_id == school_id)
        .first()
    )
    if not session:
        abort(404)
    return session
```

Then apply those helpers to admin users, packs, sessions, follow requests, codes, quizzes, and analytics.

## Verdict

The project is close enough to start the multi-school update, but not safe enough to consider it already ready. The core schema exists; the route-level access checks and school filters still need work.
