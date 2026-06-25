# IRead Global Packs Super Admin Task

This file is a planning/spec file only.

Do not implement this task until the owner approves the design.

## Goal

Add IRead global packs managed by the `super_admin`.

A global pack is an official IRead platform pack. It is created once by the IRead super admin and can be used by any school. When a school admin adds a global pack to their school, the school should be able to use it like its own pack for reader/student assignment and dashboard flows, without being allowed to edit the master global pack content.

## Product Rules

- Super admin can create and manage global packs.
- Super admin can assign IRead platform books to global packs.
- Super admin can create units for global packs.
- Super admin can create sessions for global pack units.
- Super admin can assign global teachers to global pack sessions.
- Global teachers can teach students from all schools that joined the global pack.
- School admins can add a global pack to their school.
- School admins can assign students/readers to a joined global pack like it is a school pack.
- School admins cannot edit global pack metadata, books, units, sessions, PDF stories, or headwords.
- Readers/students can access global packs only through a school they belong to.
- The rule "a student can join only one session inside a unit" is recognized, but do not implement it in this task yet.

## Existing Context

The backend already has:

- `super_admin` role.
- School admins scoped by `User_shcool`.
- `Book.is_platform_book` for IRead platform books.
- `SchoolBookInstance` for schools using platform books.
- `Pack.shcool_id` for school-owned packs.
- `Book_pack` to attach books to packs.
- `Unit` and `Session` models.
- Reader follow/enrollment models such as `Follow_pack`, `Follow_session`, and `Follow_book`.

## Recommended Data Model

Prefer a master/link model, not physical duplication.

### Update `Pack`

Add platform/global ownership fields:

```py
is_global_pack = db.Column(db.Boolean, nullable=False, default=False, index=True)
created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True, index=True)
active = db.Column(db.Boolean, nullable=False, default=True, index=True)
```

Rules:

- Global pack:
  - `Pack.is_global_pack = True`
  - `Pack.shcool_id = None`
  - `Pack.created_by = current super admin id`
- School pack:
  - `Pack.is_global_pack = False`
  - `Pack.shcool_id = current school id`
  - `Pack.created_by = current school admin id`

Do not rely only on `Pack.shcool_id IS NULL`; old rows may already have null values.

### Add `SchoolPackInstance`

Create a new model/table:

```py
class SchoolPackInstance(db.Model):
    __tablename__ = "school_pack_instance"
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    pack_id = db.Column(db.Integer, db.ForeignKey(Pack.id), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("shcool_id", "pack_id", name="uq_school_global_pack"),
    )
```

Rules:

- `pack_id` must point to a global pack.
- One school cannot add the same global pack twice.
- The instance grants access to the school.
- The instance must not copy pack, book, unit, or session rows.

### Global Teachers

Global teachers are users with role `teacher` who are allowed to teach platform/global sessions.

Recommended model:

```py
class GlobalTeacher(db.Model):
    __tablename__ = "global_teacher"
    teacher_id = db.Column(db.Integer, db.ForeignKey(User.id), primary_key=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
```

Rules:

- Only `super_admin` can add/remove global teachers.
- A global teacher can teach sessions from global packs.
- A global teacher is not limited to one school.

Alternative: add `is_global_teacher` to `Teacher`, but a separate table is cleaner and avoids changing existing teacher semantics too much.

### Units And Sessions

Current `Unit` has `book_id`. For global packs, units should belong to the pack or to a book inside the pack, depending on the current domain design.

Recommended minimal approach:

- Keep existing `Unit.book_id` behavior for now.
- Global pack sessions can reference:
  - `Session.pack_id = global pack id`
  - `Session.book_id = platform book id`
  - `Session.unit_id = unit id`
  - `Session.teacher_id = global teacher id`

Important:

- Do not implement "student can join only one session per unit" yet.
- Leave a clear TODO for this rule.

## Backend Routes

### Super Admin Global Pack Routes

List global packs:

```http
GET /admin/super/global-packs?page=1&per_page=20&search=...
```

Create global pack:

```http
POST /admin/super/global-packs
Content-Type: application/json
```

Body:

```json
{
  "title": "Global Pack",
  "level": "A1",
  "desc": "Description",
  "age": "kid",
  "img": "https://...",
  "price": 0,
  "discount": 0,
  "duration": 12,
  "faq": [],
  "public": true
}
```

Get one global pack:

```http
GET /admin/super/global-packs/<pack_id>
```

Update global pack:

```http
PUT /admin/super/global-packs/<pack_id>
```

Deactivate/delete global pack:

```http
DELETE /admin/super/global-packs/<pack_id>
```

Recommended delete behavior:

- Soft delete/deactivate if schools are using the pack.
- Hard delete only if there are no school instances, follow rows, sessions, or reader progress connected to it.

### Super Admin Global Pack Books

Attach platform book to global pack:

```http
POST /admin/super/global-packs/<pack_id>/books/<book_id>
```

Rules:

- `<pack_id>` must be a global pack.
- `<book_id>` should be an IRead platform book.
- Use existing `Book_pack`.

Detach book from global pack:

```http
DELETE /admin/super/global-packs/<pack_id>/books/<book_id>
```

List global pack books:

```http
GET /admin/super/global-packs/<pack_id>/books?page=1&per_page=20
```

### Super Admin Global Pack Units

Create unit:

```http
POST /admin/super/global-packs/<pack_id>/units
```

List units:

```http
GET /admin/super/global-packs/<pack_id>/units
```

Update unit:

```http
PUT /admin/super/global-packs/<pack_id>/units/<unit_id>
```

Delete unit:

```http
DELETE /admin/super/global-packs/<pack_id>/units/<unit_id>
```

### Super Admin Global Pack Sessions

Create session:

```http
POST /admin/super/global-packs/<pack_id>/units/<unit_id>/sessions
```

Body:

```json
{
  "name": "Session 1",
  "book_id": 10,
  "teacher_id": 55,
  "location": "online",
  "start_date": "2026-07-01T10:00:00",
  "end_date": "2026-07-01T11:00:00",
  "capacity": 30,
  "description": "Intro session",
  "active": true,
  "meet_link": "https://..."
}
```

Rules:

- Teacher must be an active global teacher.
- Book must belong to the global pack.
- Unit must belong to the pack.

List sessions:

```http
GET /admin/super/global-packs/<pack_id>/sessions?page=1&per_page=20
```

Update session:

```http
PUT /admin/super/global-packs/<pack_id>/sessions/<session_id>
```

Delete session:

```http
DELETE /admin/super/global-packs/<pack_id>/sessions/<session_id>
```

### Super Admin Global Teachers

List global teachers:

```http
GET /admin/super/global-teachers?page=1&per_page=20&search=...
```

Add existing teacher as global teacher:

```http
POST /admin/super/global-teachers
```

Body:

```json
{
  "teacher_id": 55
}
```

Remove global teacher:

```http
DELETE /admin/super/global-teachers/<teacher_id>
```

### School Admin Global Pack Routes

List available global packs:

```http
GET /admin/global-packs?page=1&per_page=20&search=...
```

Response should include:

```json
{
  "packs": [
    {
      "id": 1,
      "title": "Global Pack",
      "source": "global",
      "read_only": true,
      "already_added": false,
      "book_number": 5
    }
  ],
  "pagination": {}
}
```

Add global pack to current school:

```http
POST /admin/global-packs/<pack_id>/instances
```

Remove global pack from current school:

```http
DELETE /admin/global-packs/<pack_id>/instances
```

List current school's added global packs:

```http
GET /admin/school-global-packs?page=1&per_page=20&search=...
```

Get global pack details through current school:

```http
GET /admin/school-global-packs/<pack_id>
```

## Existing Route Updates

Update school admin pack routes to include global packs where appropriate:

- `/admin/packs`
- `/admin/show_all_packs`
- `/admin/get_pack_details`
- `/admin/get_books_from_pack`
- `/admin/create_follow_pack`
- pack follow approval/rejection routes
- dashboard analytics that count pack enrollments

Rules:

- School-owned packs remain editable by school admins.
- Global packs are visible to the school only if the school has an active `SchoolPackInstance`.
- Global packs return:

```json
{
  "source": "global",
  "is_global_pack": true,
  "read_only": true,
  "instance_id": 10
}
```

- School admins cannot edit/delete global pack metadata, units, sessions, books, or teachers.

## Reader Route Updates

Reader/student access should support global packs through a selected school.

A reader can access a global pack when:

- reader belongs to selected school, and
- selected school has active `SchoolPackInstance` for the global pack.

Reader pack lists should include:

- school-owned packs
- global packs joined by the selected school

Reader enrollment/follow should work with global pack IDs.

Do not implement the "one session per unit" rule yet.

## Frontend Dashboard Tasks

Super admin UI:

- Global Packs page.
- Create/edit global pack form.
- Assign platform books to global pack.
- Manage units for global pack.
- Manage sessions for global pack units.
- Manage global teachers.
- See schools using each global pack.

School admin UI:

- IRead Global Packs Library page.
- Add/remove global pack from school.
- Show added global packs in school pack list.
- Allow assigning students/readers to global packs like school packs.
- Show global packs as read-only.
- Hide edit/delete controls for global pack metadata, books, units, sessions, and teachers.

## Permissions Checklist

- Only `super_admin` can create/update/delete global packs.
- Only `super_admin` can attach/detach platform books to global packs.
- Only `super_admin` can create/update/delete units and sessions in global packs.
- Only `super_admin` can manage global teachers.
- School admins can add/remove global packs only for their own school.
- School admins can assign their own students/readers to global packs joined by their school.
- Readers can access global packs only through a school they belong to.

## Migration Checklist

Create a migration that:

- Adds `pack.is_global_pack`.
- Adds `pack.created_by`.
- Adds `pack.active`.
- Creates `school_pack_instance`.
- Creates `global_teacher`.
- Adds needed indexes:
  - `pack.is_global_pack`
  - `pack.created_by`
  - `pack.active`
  - `school_pack_instance.shcool_id`
  - `school_pack_instance.pack_id`
  - unique `school_pack_instance(shcool_id, pack_id)`

Backfill decision:

- Do not mark old `Pack.shcool_id IS NULL` rows as global packs unless they are confirmed official IRead packs.

## Acceptance Criteria

- Super admin can create a global pack.
- Super admin can attach platform books to a global pack.
- Super admin can create units and sessions for a global pack.
- Super admin can assign global teachers to global pack sessions.
- School admin can browse available global packs.
- School admin can add a global pack to their school.
- School admin can remove a global pack from their school.
- School admin can assign students/readers to a joined global pack.
- School admin cannot edit global pack content.
- Reader/student can access joined global packs through their selected school.
- Lists are paginated.
- No global pack leaks to a school that has not joined it.

## Explicitly Out Of Scope For First Implementation

Do not implement these until separately approved:

- Student can join only one session per unit.
- Billing/revenue sharing for global packs.
- Duplicating global packs into real school-owned pack rows.
- School-level customization of global pack content.
