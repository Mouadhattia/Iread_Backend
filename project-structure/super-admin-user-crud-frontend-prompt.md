# Super Admin User CRUD Frontend Prompt

Copy this prompt into Codex inside the React admin dashboard app.

## Prompt

Please update the super-admin dashboard user management screens for the new backend user CRUD routes.

Do not change backend code. Update only the React admin frontend, API client, routes, state, tables, forms, and UI.

### Auth

These routes are only for authenticated approved `super_admin` users. Every request must include cookies:

```js
fetch(url, {
  credentials: "include",
  headers: { "Content-Type": "application/json" }
});
```

### Existing List Route

Keep using the paginated users route:

```http
GET /admin/super/users?page=1&per_page=20
GET /admin/super/users?role=admin&approved=false&page=1&per_page=20
GET /admin/super/users?school=<schoolId>&search=<term>&page=1&per_page=20
```

Response:

```json
{
  "users": [
    {
      "id": 10,
      "username": "school-admin",
      "email": "admin@example.com",
      "img": null,
      "role": "admin",
      "confirmed": true,
      "approved": false,
      "status": "pending_approval",
      "created_at": "2026-06-10T12:00:00",
      "quiz_id": null,
      "schools": [
        { "id": 3, "name": "School Name" }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "pages": 5,
    "has_next": true,
    "has_prev": false,
    "max_per_page": 100
  }
}
```

### Get One User

```http
GET /admin/super/users/<userId>
```

Alias:

```http
GET /admin/super/user/<userId>
```

Response:

```json
{
  "user": {
    "id": 10,
    "username": "school-admin",
    "email": "admin@example.com",
    "role": "admin",
    "confirmed": true,
    "approved": false,
    "status": "pending_approval",
    "schools": [
      { "id": 3, "name": "School Name" }
    ],
    "user_id_invoicing_api": null
  }
}
```

### Create User

```http
POST /admin/super/users
```

Body examples:

```json
{
  "role": "reader",
  "username": "reader1",
  "email": "reader@example.com",
  "password": "secret",
  "school_ids": [3],
  "confirmed": true,
  "approved": true
}
```

```json
{
  "role": "admin",
  "username": "school-admin",
  "email": "admin@example.com",
  "password": "secret",
  "school_ids": [3],
  "confirmed": true,
  "approved": false
}
```

```json
{
  "role": "teacher",
  "username": "teacher1",
  "email": "teacher@example.com",
  "password": "secret",
  "school_ids": [3],
  "description": "Teacher bio",
  "study_level": "A1",
  "available": true
}
```

Supported roles:

- `reader`
- `teacher`
- `assistant`
- `admin`
- `super_admin`

For all roles except `super_admin`, send `school_ids`.

### Update User

```http
PUT /admin/super/users/<userId>
```

Alias:

```http
PUT /admin/super/user/<userId>
```

Body can include:

```json
{
  "username": "updated-name",
  "email": "updated@example.com",
  "img": "https://optional-image",
  "confirmed": true,
  "approved": true,
  "password": "optional-new-password",
  "school_ids": [3, 4]
}
```

Teacher-only fields:

```json
{
  "description": "Updated bio",
  "study_level": "B1",
  "available": true
}
```

Reader-only fields:

```json
{
  "level": "A2",
  "client_id_invoicing_api": "optional"
}
```

Admin/assistant field:

```json
{
  "user_id_invoicing_api": "optional"
}
```

Do not send `role` or `type` in update. Backend does not support changing a user role from this endpoint.

If a pending school admin is updated from `approved: false` to `approved: true`, the backend sends the school admin an approval email.

### Approve User

Use this for pending school admin approval and other pending users:

```http
POST /admin/super/approve_user
```

Body:

```json
{ "user_id": 10 }
```

Aliases:

```http
POST /admin/super/approve_school_admin
POST /admin/super/users/<userId>/approve
```

The backend sets:

```json
{
  "confirmed": true,
  "approved": true,
  "status": "approved"
}
```

When the approved user role is `admin`, the backend sends an email telling the school admin that their school admin account has been approved.

Response includes:

```json
{
  "message": "School admin account approved successfully",
  "user": {},
  "approval_email_sent": true
}
```

If email sending fails, the user is still approved and the response may include:

```json
{
  "approval_email_sent": false,
  "approval_email_error": "error details"
}
```

### Delete User

```http
DELETE /admin/super/users/<userId>
```

Alias:

```http
DELETE /admin/super/user/<userId>
```

Body-based alias:

```http
POST /admin/super/delete_user
```

```json
{ "user_id": 10 }
```

Backend prevents deleting the current super admin account and prevents deleting the last super admin.

### Frontend Tasks

- Add Create, View/Edit, Approve, and Delete actions to the super-admin users page.
- Add a pending school-admin tab/filter using `role=admin&approved=false`.
- Show `status` badges: approved vs pending approval.
- Build a user form that supports role-specific fields.
- Use a school multi-select for all non-super-admin users.
- After create/update/approve/delete, refresh the current users page.
- Show success feedback when approval email is sent.
- Show warning feedback when approval succeeds but email sending fails.
- Confirm before deleting a user.
- Handle `401` by redirecting to login.
- Handle `403` with access denied.
- Handle `400` and `409` validation messages inline.
- Keep pagination working with `pagination.page`, `pagination.pages`, `has_next`, and `has_prev`.

Do not change backend code.
Run frontend build/lint/tests after the update.
