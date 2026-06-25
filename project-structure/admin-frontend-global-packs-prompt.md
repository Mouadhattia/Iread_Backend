# Admin Dashboard Frontend Prompt: Global Packs

Copy this prompt into Codex inside the React admin dashboard app.

## Prompt

You are updating the IRead React admin dashboard to support the new Global Packs backend.

The backend is already updated. Do not change backend code. Update only the React admin frontend, API client, routing, state, forms, tables, and UI.

Important: `super_admin` and normal school `admin` use the same dashboard app. The UI must switch behavior based on the authenticated user's role.

Every request must include session cookies:

```js
fetch(url, {
  credentials: "include"
});
```

For JSON:

```js
fetch(url, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data)
});
```

## Auth

Use the existing auth endpoint:

```http
GET /reader/user_authenticated
```

Use `role` to decide the dashboard experience:

- `super_admin`: show global pack management.
- `admin`: show global pack library and joined global packs for the current school.

## Main Concept

A global pack is an official IRead platform pack created by the super admin.

Schools can add global packs to their school. Once added, school admins can assign their own students/readers to that global pack like a normal school pack, but they cannot edit the global pack content.

Global packs should appear as read-only in school admin views.

Backend marks global packs with:

```json
{
  "source": "global",
  "is_global_pack": true,
  "read_only": true,
  "instance_id": 10
}
```

## Super Admin Features

Add navigation item:

```text
Global Packs
```

Super admin can:

- List global packs.
- Search and paginate global packs.
- Create a global pack.
- Edit global pack metadata.
- Deactivate/delete global pack.
- Assign IRead platform books to a global pack.
- Create/list/update/delete units for a global pack.
- Create/list/update/delete sessions for global pack units.
- Manage global teachers.
- See schools using each global pack.

### Super Admin Global Pack Endpoints

List:

```http
GET /admin/super/global-packs?page=1&per_page=20&search=...
```

Create:

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

Get details:

```http
GET /admin/super/global-packs/:packId
```

Update:

```http
PUT /admin/super/global-packs/:packId
```

Deactivate/delete:

```http
DELETE /admin/super/global-packs/:packId
```

### Super Admin Books In Global Pack

List books in global pack:

```http
GET /admin/super/global-packs/:packId/books?page=1&per_page=20
```

Attach platform book:

```http
POST /admin/super/global-packs/:packId/books/:bookId
```

Detach platform book:

```http
DELETE /admin/super/global-packs/:packId/books/:bookId
```

Important:

- Use IRead platform books only.
- Platform books can be loaded from the existing platform book endpoint:

```http
GET /admin/super/platform-books?page=1&per_page=20&search=...
```

### Super Admin Units

List units:

```http
GET /admin/super/global-packs/:packId/units
```

Create unit:

```http
POST /admin/super/global-packs/:packId/units
```

Body:

```json
{
  "name": "Unit 1",
  "book_id": 10
}
```

Update unit:

```http
PUT /admin/super/global-packs/:packId/units/:unitId
```

Delete unit:

```http
DELETE /admin/super/global-packs/:packId/units/:unitId
```

### Super Admin Sessions

List sessions:

```http
GET /admin/super/global-packs/:packId/sessions?page=1&per_page=20
```

Create session under a unit:

```http
POST /admin/super/global-packs/:packId/units/:unitId/sessions
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

Update session:

```http
PUT /admin/super/global-packs/:packId/sessions/:sessionId
```

Delete session:

```http
DELETE /admin/super/global-packs/:packId/sessions/:sessionId
```

### Super Admin Global Teachers

List:

```http
GET /admin/super/global-teachers?page=1&per_page=20&search=...
```

Add teacher as global teacher:

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
DELETE /admin/super/global-teachers/:teacherId
```

Use existing teacher/user lists to select teachers.

## School Admin Features

Add navigation item:

```text
Global Packs
```

For school admin, this page should be a Global Packs Library.

School admin can:

- Browse available IRead global packs.
- Search and paginate.
- Add a global pack to the current school.
- Remove a global pack from the current school.
- See global packs already added to the school.
- View global pack details, books, units, and sessions.
- Assign this school's students/readers to joined global packs using existing student assignment/follow-pack flows.

School admin cannot:

- Edit global pack metadata.
- Add/remove books from a global pack.
- Create/edit/delete global units.
- Create/edit/delete global sessions.
- Manage global teachers.

### School Admin Endpoints

List available global packs:

```http
GET /admin/global-packs?page=1&per_page=20&search=...
```

Add global pack to school:

```http
POST /admin/global-packs/:packId/instances
```

Remove global pack from school:

```http
DELETE /admin/global-packs/:packId/instances
```

List global packs already added to current school:

```http
GET /admin/school-global-packs?page=1&per_page=20&search=...
```

Get joined global pack details:

```http
GET /admin/school-global-packs/:packId
```

## Existing School Admin Pack Views

Update existing pack pages that call:

```http
GET /admin/packs
GET /admin/show_all_packs
GET /admin/get_pack_details?id=:packId
GET /admin/get_books_from_pack?id=:packId
POST /admin/create_follow_pack
GET /admin/show_pack_follow_requests
POST /admin/approve_pack_follow_request
POST /admin/reject_pack_follow_request
POST /admin/delete_follow_request
POST /admin/get_users_in_pack
GET /admin/sessions
GET /admin/show_session_follow_requests
POST /admin/create_follow_session
```

These existing routes now may return both school packs and joined global packs.

If a pack has:

```json
{
  "is_global_pack": true,
  "source": "global",
  "read_only": true
}
```

Then:

- Show it as an IRead global pack.
- Hide or disable edit/delete pack controls.
- Hide or disable book/unit/session mutation controls.
- Keep student assignment controls available.
- Keep follow-pack approval/rejection available only for this school's students.

Normal school packs must remain fully editable.

## UI Guidance

Use one dashboard app and role-aware navigation:

- `super_admin`: Global Packs should be a management area.
- `admin`: Global Packs should be a library/usage area.

Suggested super admin screens:

- Global Packs list.
- Global Pack detail.
- Pack metadata form.
- Books tab.
- Units tab.
- Sessions tab.
- Global Teachers page or modal.
- Schools using this pack section.

Suggested school admin screens:

- Available Global Packs.
- My School Global Packs.
- Global Pack detail.
- Student assignment area.

## Response Shape Examples

Global pack row:

```json
{
  "id": 1,
  "title": "Global Pack",
  "level": "A1",
  "school_id": 3,
  "owner_school_id": null,
  "source": "global",
  "is_global_pack": true,
  "read_only": true,
  "instance_id": 10,
  "already_added": true,
  "book_number": 4
}
```

Global pack details:

```json
{
  "pack": {
    "id": 1,
    "title": "Global Pack",
    "source": "global",
    "read_only": true,
    "books": [],
    "units": [],
    "sessions": []
  }
}
```

## Error Handling

Show backend `message` or `error`.

Common messages:

```text
Global pack not found
Global pack is already added to this school
Global pack removed from this school
Teacher is not an active global teacher
Book not found in this global pack
Cannot delete unit while sessions use it
```

## Out Of Scope

Do not implement the rule "student can join only one session per unit" on the frontend unless the backend adds an explicit response or endpoint for it.

Do not allow school admins to customize global pack content.

Do not duplicate global pack data in frontend state as if it were a school-owned pack.

## Acceptance Criteria

- Same dashboard app supports both `super_admin` and school `admin`.
- Super admin can create/edit/deactivate global packs.
- Super admin can attach platform books to global packs.
- Super admin can manage global pack units and sessions.
- Super admin can manage global teachers.
- School admin can browse available global packs.
- School admin can add/remove global packs for their school.
- School admin can view joined global pack details.
- Joined global packs appear in existing pack lists as read-only.
- School admin can assign their own students/readers to joined global packs.
- School admin cannot edit global pack content.
- All list views use backend pagination.
