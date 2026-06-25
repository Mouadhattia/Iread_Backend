# Admin Frontend Multi-School Update Prompt

Use this prompt inside the React admin dashboard app.

## Prompt

You are updating the IRead school admin dashboard for the new multi-school backend behavior. The backend now scopes admin data by the logged-in admin's school and includes new reader school-join flows. Update the admin frontend so every dashboard workflow behaves as a school-specific admin dashboard.

### Main Goal

Make the admin dashboard operate only inside the current admin's school. Do not let school admins choose or submit another `school_id` for normal dashboard actions. The backend derives the school from the authenticated admin session.

### Authentication Contract

On app startup, call:

```http
GET /reader/user_authenticated
```

Always include credentials:

```js
fetch(url, {
  credentials: "include",
  headers: { "Content-Type": "application/json" }
});
```

Expected admin response:

```json
{
  "is_authenticated": true,
  "role": "admin",
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "school_id": 1,
  "school": "School Name"
}
```

Expected super admin response:

```json
{
  "is_authenticated": true,
  "role": "super_admin",
  "id": 1,
  "username": "super",
  "email": "super@example.com",
  "is_super_admin": true,
  "schools": [
    { "id": 1, "name": "School Name" }
  ]
}
```

Store:

- `adminUser`
- `activeSchoolId`
- `activeSchoolName`

Show the school name in the dashboard header/sidebar.

### Super Admin Signup

For first-time super admin setup, use:

```http
POST /reader/register_super_admin
```

Alias:

```http
POST /reader/signup_super_admin
```

Request body:

```json
{
  "username": "super-admin",
  "email": "super@example.com",
  "password": "secret",
  "img": "https://optional-image-url"
}
```

The backend allows public creation only when no super admin exists yet. After a super admin exists, creating another super admin requires an authenticated super admin session.

### Super Admin Global Routes

Use these routes only when `role === "super_admin"`:

```http
GET /admin/super/dashboard
GET /admin/super/users?page=1&per_page=20
GET /admin/super/books?page=1&per_page=20
GET /admin/super/packs?page=1&per_page=20
GET /admin/super/schools?page=1&per_page=20
```

Optional filters:

```http
GET /admin/super/users?role=reader&school=<schoolId>&search=<term>&page=1&per_page=20
GET /admin/super/books?school=<schoolId>&search=<term>&page=1&per_page=20
GET /admin/super/packs?school=<schoolId>&search=<term>&page=1&per_page=20
GET /admin/super/schools?search=<term>&page=1&per_page=20
GET /admin/super/users?role=admin&approved=false&page=1&per_page=20
```

Super admin can see global users, books, packs, schools, and counts. Normal school admins receive `403` for these routes.

Super admins can approve pending school admin accounts:

```http
POST /admin/super/approve_school_admin
```

Body:

```json
{ "admin_id": 10 }
```

The backend also accepts `id` or `user_id` in the body.

All super-admin list routes are paginated. The backend defaults to `page=1` and `per_page=20`, and caps `per_page` at `100`. Read the `pagination` object from each list response:

```json
{
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 250,
    "pages": 13,
    "has_next": true,
    "has_prev": false,
    "max_per_page": 100
  }
}
```

### School Admin Signup

For public school-admin onboarding, use:

```http
POST /reader/register_school_admin
```

Alias:

```http
POST /reader/signup_school_admin
```

Request body:

```json
{
  "school_name": "School Name",
  "username": "school-owner",
  "email": "owner@example.com",
  "password": "secret",
  "img": "https://optional-image-url"
}
```

Successful pending response:

```json
{
  "message": "School admin account has been created and is pending super admin approval",
  "admin": {
    "id": 10,
    "username": "school-owner",
    "email": "owner@example.com",
    "role": "admin",
    "confirmed": true,
    "approved": false,
    "status": "pending_approval"
  },
  "school": {
    "id": 3,
    "name": "School Name",
    "status": "pending_admin_approval"
  }
}
```

The backend creates the school first, creates the admin user, links the admin to that school through `user_shcool`, and leaves the admin account pending. Do not auto-enter the dashboard after this signup. Show a pending approval message. The account can log in only after a super admin approves it.

### Admin School Scoping Rules

The backend now validates admin routes by the current admin's school. Update frontend forms and requests accordingly:

- Do not send `school_id` when creating packs.
- Do not show a school selector in normal school-admin create/edit forms.
- Admin-created readers are automatically joined to the admin's school.
- Admin-created teachers and assistants are automatically joined to the admin's school.
- Pack, session, code, follow-request, notification, log, and analytics routes are school-scoped by the backend.
- `/admin/show_all_books` now returns only books linked to the current admin's school packs through `Book_pack -> Pack.shcool_id`.
- `/admin/get_book/<id>`, `/admin/update_book`, and `/admin/delete_book` are also scoped to the current admin's school books.
- School management routes are now super-admin only:
  - `POST /admin/create_shcool`
  - `GET /admin/get_all_shcools`
  - `GET /admin/get_one_shcool/<id>`
  - `PUT /admin/update_shcool/<id>`
  - `DELETE /admin/delete_shcool/<id>`

Update these areas:

- Readers list/create/update/delete
- Teachers list/create/update/delete
- Assistants list/create/update/delete
- Packs list/create/update/delete
- Sessions list/create/update/delete
- Pack follow requests
- Session follow requests
- Codes in packs
- Notifications
- Logs and dashboard analytics

### School Invitation Codes

Add an invitation-code management screen or section for school admins.

List invitation codes:

```http
GET /admin/school_invitation_codes
```

Generate invitation code:

```http
POST /admin/generate_school_invitation_code
```

Optional body:

```json
{
  "code": "CUSTOMCODE",
  "max_uses": 25
}
```

If `code` is omitted, the backend generates one. If `max_uses` is omitted or null, the code is reusable without a fixed limit.

Update invitation code:

```http
PUT /admin/school_invitation_code/<id>
```

Body:

```json
{
  "active": false,
  "max_uses": 10
}
```

Delete invitation code:

```http
DELETE /admin/school_invitation_code/<id>
```

Invitation code response shape:

```json
{
  "id": 1,
  "code": "SCHOOLCODE",
  "shcool_id": 1,
  "school": "School Name",
  "active": true,
  "max_uses": 25,
  "used_count": 3,
  "created_by": 10,
  "created_at": "2026-06-05T12:00:00"
}
```

### Reader-Side Backend Updates To Know

These are not necessarily admin dashboard screens, but they are part of today's backend contract and may affect shared API/state code.

Readers can list all schools:

```http
GET /reader/get_all_schools
```

Readers can join one or many schools directly:

```http
POST /reader/join_school
```

```json
{ "school_id": 2 }
```

or:

```json
{ "school_ids": [2, 3, 4] }
```

Readers can join by invitation code:

```http
POST /reader/join_school_by_invitation
```

```json
{ "code": "SCHOOLCODE" }
```

Reader signup and Google signup can optionally include:

```json
{ "invitation_code": "SCHOOLCODE" }
```

### Reader School-Scoped Content Updates

Shared frontend code should know these reader endpoints are now school-aware:

```http
GET /reader/get_packs_by_school?school=<activeSchoolId>&all=0
GET /reader/get_pack_details?school=<activeSchoolId>&id=<packId>
GET /reader/get_books_from_pack?school=<activeSchoolId>&id=<packId>
GET /reader/get_followed_pack_list?school=<activeSchoolId>
GET /reader/get_unfollowed_books?school=<activeSchoolId>
GET /reader/dashboard?school=<activeSchoolId>
```

`/reader/get_pack_details` now includes both:

- `books`
- `books_in_pack`

The legacy `/main/get_pack_details` also now includes `books` and `books_in_pack`, but school-specific reader pages should prefer the `/reader/...` endpoints.

### Error Handling

Handle these statuses consistently:

- `401`: redirect to login or show signed-out state.
- `403`: show "No school access" or "You do not have access to this school."
- `404`: show not found or not available in this school.
- `409`: show conflict messages, such as duplicate email/code/title.
- `500`: show retry state and log details in development.

### Admin Frontend Checklist

- Admin app loads current admin from `/reader/user_authenticated`.
- Dashboard displays current school name.
- Create pack no longer sends `school_id`.
- Create reader/teacher/assistant no longer asks for school.
- Lists only show data returned by school-scoped backend routes.
- Pack/session/code/follow-request operations handle `403` and `404`.
- Invitation-code management UI supports list/create/update/delete.
- Super-admin list pages use `page` and `per_page` and do not fetch all users/books/packs/schools at once.
- Super-admin users page can filter pending school admins with `role=admin&approved=false`.
- Super-admin users page can approve pending school admins using `/admin/super/approve_school_admin`.
- School-admin signup shows pending approval instead of logging in directly.
- API calls all use `credentials: "include"`.
- Build/lint/tests pass.

Do not change backend code.
