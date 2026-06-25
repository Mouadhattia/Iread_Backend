# Admin Frontend Super Admin Finish Prompt

Copy this prompt into Codex inside the React admin dashboard app.

## Prompt

You are updating the IRead React admin dashboard to finish the latest backend changes for multi-school and super-admin management.

The backend is already updated. Do not change backend code. Update only the React admin frontend, API client code, routing, state, and UI needed for the admin dashboard.

### Main Goal

Support two admin experiences:

- `admin`: normal school admin. This user only works inside their own school. Do not show global school selectors for normal dashboard actions.
- `super_admin`: global platform admin. This user can see all schools, users, packs, books, and global counts.

Every request must include cookies/session credentials:

```js
fetch(url, {
  credentials: "include",
  headers: { "Content-Type": "application/json" }
});
```

### Auth Check

On app startup, call:

```http
GET /reader/user_authenticated
```

Normal school admin response:

```json
{
  "is_authenticated": true,
  "role": "admin",
  "id": 10,
  "username": "school-admin",
  "email": "admin@example.com",
  "img": "https://optional-image-url",
  "school_id": 3,
  "school": "School Name"
}
```

Super admin response:

```json
{
  "is_authenticated": true,
  "role": "super_admin",
  "id": 1,
  "username": "super-admin",
  "email": "super@example.com",
  "img": "https://optional-image-url",
  "is_super_admin": true,
  "schools": [
    { "id": 1, "name": "School A" },
    { "id": 2, "name": "School B" }
  ]
}
```

Store the authenticated user in shared auth state. Use `role` to decide navigation, protected routes, and which API routes are available.

### Super Admin Signup

Add or update a setup/signup screen for super admins.

Endpoint:

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

Successful response:

```json
{
  "message": "Super admin account has been created successfully",
  "super_admin": {
    "id": 1,
    "username": "super-admin",
    "email": "super@example.com",
    "role": "super_admin",
    "img": "https://optional-image-url",
    "confirmed": true,
    "approved": true
  }
}
```

Important behavior:

- Public creation is allowed only when no super admin exists yet.
- After one super admin exists, creating another super admin requires an authenticated `super_admin` session.
- If the backend returns `403` with `Super admin already exists`, send the user to the normal login screen.

### Super Admin Global Routes

Use these routes only when `role === "super_admin"`.

All super-admin list routes are now paginated. Always send `page` and `per_page` from the frontend. The backend defaults to `page=1` and `per_page=20`, and caps `per_page` at `100`.

Pagination response shape:

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

Global dashboard:

```http
GET /admin/super/dashboard
```

Response shape:

```json
{
  "users": 100,
  "readers": 80,
  "admins": 5,
  "pending_admins": 2,
  "super_admins": 1,
  "teachers": 10,
  "assistants": 4,
  "schools": 3,
  "packs": 20,
  "books": 200,
  "sessions": 30
}
```

Global users:

```http
GET /admin/super/users?page=1&per_page=20
GET /admin/super/users?role=reader&school=<schoolId>&search=<term>&page=1&per_page=20
GET /admin/super/users?role=admin&approved=false&page=1&per_page=20
```

Response shape:

```json
{
  "users": [
    {
      "id": 12,
      "username": "reader",
      "email": "reader@example.com",
      "img": null,
      "role": "reader",
      "confirmed": true,
      "approved": true,
      "status": "approved",
      "created_at": "2026-06-08T12:00:00",
      "quiz_id": 1,
      "schools": [
        { "id": 3, "name": "School Name" }
      ]
    }
  ],
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

Use `approved=false` to load pending accounts. For pending school admin approvals, use:

```http
GET /admin/super/users?role=admin&approved=false&page=1&per_page=20
```

Approve a pending school admin:

```http
POST /admin/super/approve_school_admin
```

Body:

```json
{ "admin_id": 10 }
```

Aliases accepted by the backend:

```json
{ "id": 10 }
```

or:

```json
{ "user_id": 10 }
```

Successful response:

```json
{
  "message": "School admin account approved successfully",
  "admin": {
    "id": 10,
    "username": "school-admin",
    "email": "admin@example.com",
    "role": "admin",
    "confirmed": true,
    "approved": true,
    "status": "approved",
    "schools": [
      { "id": 3, "name": "School Name" }
    ]
  }
}
```

Global books:

```http
GET /admin/super/books?page=1&per_page=20
GET /admin/super/books?school=<schoolId>&search=<term>&page=1&per_page=20
```

Response shape:

```json
{
  "books": [
    {
      "id": 5,
      "title": "Book Title",
      "author": "Author",
      "img": null,
      "release_date": "2026-06-08",
      "page_number": 100,
      "category": "Category",
      "neo4j_id": null,
      "desc": "Description",
      "packs": [
        {
          "id": 2,
          "title": "Pack Title",
          "school_id": 3,
          "school": "School Name"
        }
      ],
      "schools": [
        { "id": 3, "name": "School Name" }
      ]
    }
  ],
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

Global packs:

```http
GET /admin/super/packs?page=1&per_page=20
GET /admin/super/packs?school=<schoolId>&search=<term>&page=1&per_page=20
```

Response shape:

```json
{
  "packs": [
    {
      "id": 2,
      "title": "Pack Title",
      "level": "Level",
      "age": "Age",
      "price": 10,
      "img": null,
      "book_number": 4,
      "discount": 0,
      "desc": "Description",
      "faq": null,
      "duration": 30,
      "product_id_invoicing_api": null,
      "public": true,
      "school_id": 3,
      "school": "School Name",
      "codes": 5,
      "enrolled": 20
    }
  ],
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

Global schools:

```http
GET /admin/super/schools?page=1&per_page=20
GET /admin/super/schools?search=<term>&page=1&per_page=20
```

Response shape:

```json
{
  "schools": [
    {
      "id": 3,
      "name": "School Name",
      "user_count": 40,
      "pack_count": 8,
      "book_count": 60
    }
  ],
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

### School Management

School CRUD is now super-admin only. Hide these screens/actions for normal `admin` users.

Create school:

```http
POST /admin/create_shcool
```

Body:

```json
{ "name": "School Name" }
```

Get all schools:

```http
GET /admin/get_all_shcools
```

This route returns a raw array:

```json
[
  { "id": 1, "name": "School A" },
  { "id": 2, "name": "School B" }
]
```

Get one school:

```http
GET /admin/get_one_shcool/<id>
```

Update school:

```http
PUT /admin/update_shcool/<id>
```

Body:

```json
{ "name": "Updated School Name" }
```

Delete school:

```http
DELETE /admin/delete_shcool/<id>
```

### School Admin Signup Approval

Public school-admin signup creates the school and admin account, but the admin account is no longer approved immediately. The frontend must show a pending approval message and must not assume the user is logged in after signup.

Endpoint:

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
    "img": "https://optional-image-url",
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

After approval, the school admin can log in normally. Before approval, login returns `403`.

### Normal School Admin Behavior

Keep normal school admin dashboard behavior scoped to the logged-in admin's school.

Rules:

- Normal `admin` users must not see super-admin nav items.
- Normal `admin` users must not call `/admin/super/*`.
- Normal `admin` users must not manage schools.
- Normal `admin` users should see the current school name from `/reader/user_authenticated`.
- Do not send `school_id` for normal school-admin create/update actions unless an existing endpoint explicitly requires it.
- The backend derives school access from the logged-in admin session.
- `/admin/show_all_books` now returns only books connected to the admin school through packs.
- `/admin/get_book/<id>`, `/admin/update_book`, and `/admin/delete_book` are school-scoped too.

### UI Work To Finish

Implement or update:

- Auth bootstrap that supports both `admin` and `super_admin`.
- Role-based sidebar/navigation.
- Super admin dashboard page with global count cards.
- Super admin users page with role filter, approved/pending filter, school filter, search, and table.
- Pending school admin approval action using `/admin/super/approve_school_admin`.
- Super admin schools page with list, create, edit, and delete.
- Super admin packs page with school filter and search.
- Super admin books page with school filter and search.
- Pagination controls for super admin users, schools, packs, and books.
- Super admin signup/setup page.
- Normal school admin pages should keep existing workflows but no longer show global school management.

Use `/admin/super/schools?search=<term>&page=1&per_page=20` to populate super-admin school filters. Do not assume all schools are loaded at once.

### Error Handling

Handle these statuses:

- `401`: redirect to login.
- `403`: show access denied. If this happens on super-admin setup, show that a super admin already exists and redirect to login.
- `400`: show validation errors, including invalid `school_id`.
- `404`: show not found.
- `409`: show duplicate email or conflict messages.
- `500`: show retry state and log details in development.

### Acceptance Checklist

- App boots with `/reader/user_authenticated`.
- `admin` role sees only school-admin dashboard routes.
- `super_admin` role sees global dashboard and school management.
- Super admin global users, books, packs, and schools load successfully.
- Super admin filters work for school, role, and search where supported.
- Super admin can list pending school admins and approve them.
- School admin signup shows pending approval and does not enter the dashboard automatically.
- Super admin list pages use backend pagination and do not fetch all rows at once.
- Normal admin cannot see or navigate to super-admin pages.
- All API calls include `credentials: "include"`.
- Frontend build, lint, and tests pass.

Do not change backend code.
