# Codex Prompt: Admin Dashboard Global Packs

You are working on the React admin dashboard for IREAD. The same dashboard is used by both `super_admin` and school admins (`admin`), so implement role-based behavior inside the existing dashboard instead of creating a separate app.

## Goal

Add dashboard support for IREAD platform/global packs.

A `super_admin` can create and manage global packs owned by the IREAD platform. These packs can contain platform books, units, sessions, and global teachers.

A school admin can browse global packs, add a global pack to their school, remove it from their school, and assign students/readers to it like a normal school pack. School admins must not be able to edit the global pack content, books, headwords, PDFs, units, or sessions.

## Important Rules

- Do not change backend routes.
- Use the existing authenticated user endpoint to detect role, for example `GET /reader/user_authenticated`.
- Always send requests with `credentials: "include"`.
- Keep the existing school-owned pack workflow working.
- Treat global packs as read-only for school admins.
- Only `super_admin` can create, edit, deactivate, or manage global pack content.
- School admin and super admin use the same dashboard, same layout, and same auth flow.

## Role Behavior

### Super Admin

Add a navigation item such as `Global Packs`.

Super admin should be able to:

- List global packs with pagination and search.
- Create a global pack.
- View global pack details.
- Edit global pack metadata.
- Deactivate/delete a global pack.
- Attach platform books to a global pack.
- Detach books from a global pack.
- Create, update, and delete units inside a global pack.
- Create, update, and delete sessions inside global-pack units.
- Manage global teachers.
- See which schools have added/are using a global pack if the backend returns school usage data.

### School Admin

Add a navigation item such as `IRead Global Packs`, or integrate global packs into the existing Packs area with a clear read-only badge.

School admin should be able to:

- Browse available IREAD global packs.
- Search and paginate global packs.
- Add a global pack to their school.
- Remove a global pack from their school.
- See joined global packs in their normal packs list.
- Open joined global pack details.
- See books, units, and sessions inside joined global packs.
- Assign readers/students to joined global packs using the existing pack-follow workflow.
- Assign readers/students to sessions where the existing dashboard already supports session follow/join flows.

School admin must not be able to:

- Edit global pack title/description.
- Add/remove books from a global pack.
- Edit platform books in a global pack.
- Edit story PDFs/headwords for global-pack books.
- Create/edit/delete global-pack units.
- Create/edit/delete global-pack sessions.

## Backend Routes

### Auth

Use the existing logged-in user route:

```http
GET /reader/user_authenticated
```

Expected role values include:

```text
super_admin
admin
teacher
reader
```

Use this role to switch dashboard permissions.

## Super Admin Global Pack Routes

### List/Create Global Packs

```http
GET /admin/super/global-packs?page=1&per_page=20&search=
POST /admin/super/global-packs
```

Example create payload:

```json
{
  "name": "Global Reading Pack",
  "description": "Shared IREAD platform pack",
  "active": true
}
```

### Global Pack Details

```http
GET /admin/super/global-packs/:packId
PUT /admin/super/global-packs/:packId
PATCH /admin/super/global-packs/:packId
DELETE /admin/super/global-packs/:packId
```

### Global Pack Books

```http
GET /admin/super/global-packs/:packId/books
POST /admin/super/global-packs/:packId/books/:bookId
DELETE /admin/super/global-packs/:packId/books/:bookId
```

Only platform books created/owned by the super admin should be attachable to global packs.

### Global Pack Units

```http
GET /admin/super/global-packs/:packId/units
POST /admin/super/global-packs/:packId/units
PUT /admin/super/global-packs/:packId/units/:unitId
PATCH /admin/super/global-packs/:packId/units/:unitId
DELETE /admin/super/global-packs/:packId/units/:unitId
```

### Global Pack Sessions

```http
GET /admin/super/global-packs/:packId/sessions
POST /admin/super/global-packs/:packId/units/:unitId/sessions
PUT /admin/super/global-packs/:packId/sessions/:sessionId
PATCH /admin/super/global-packs/:packId/sessions/:sessionId
DELETE /admin/super/global-packs/:packId/sessions/:sessionId
```

### Global Teachers

```http
GET /admin/super/global-teachers?page=1&per_page=20&search=
POST /admin/super/global-teachers
DELETE /admin/super/global-teachers/:teacherId
```

Global teachers are existing teacher users promoted/linked as global teachers by the super admin.

## School Admin Global Pack Routes

### Browse Available Platform Packs

```http
GET /admin/global-packs?page=1&per_page=20&search=
```

Use this page to show global packs available to the current school.

### Add/Remove Global Pack From Current School

```http
POST /admin/global-packs/:packId/instances
DELETE /admin/global-packs/:packId/instances
```

After adding a pack, refresh the available global packs list and the school pack list.

### Joined Global Packs

```http
GET /admin/school-global-packs?page=1&per_page=20&search=
GET /admin/school-global-packs/:packId
```

Use these routes for the school admin’s joined global packs view.

## Existing Routes That Now Support Global Packs

The existing dashboard pack routes should continue to work and may now include global packs with read-only metadata.

```http
GET /admin/packs
GET /admin/show_all_packs
POST /admin/get_pack_details
POST /admin/get_books_from_pack
```

Global pack objects may include fields like:

```json
{
  "id": 10,
  "name": "Global Reading Pack",
  "source": "global",
  "is_global_pack": true,
  "read_only": true,
  "instance_id": 5,
  "already_added": true,
  "school_id": 1,
  "owner_school_id": null,
  "books": [],
  "units": [],
  "sessions": []
}
```

Use `read_only`, `source`, or `is_global_pack` to disable editing controls in shared components.

## Student/Reader Assignment Routes

School admins should be able to assign readers to joined global packs using the existing pack-follow flow.

```http
POST /admin/create_follow_pack
POST /admin/approve_pack_follow_request
POST /admin/reject_pack_follow_request
POST /admin/delete_follow_request
GET /admin/show_pack_follow_requests
POST /admin/get_one_pack_follow_requests
GET /admin/reader_in_pack/:packId
POST /admin/get_users_in_pack
```

If the current dashboard already has UI for these actions, make sure it also works when the selected pack is a joined global pack.

## Session Routes

Existing session views now may include global sessions for joined global packs.

```http
GET /admin/sessions
GET /admin/sessions/:sessionId
POST /admin/create_follow_session
```

If the dashboard has session follow approval/rejection/delete screens, keep them working for accessible global sessions too.

Global sessions should be read-only for school admins.

## UI Tasks

### Shared Dashboard

- Keep one dashboard app for both roles.
- Add role-based navigation.
- Add reusable permission helpers such as:

```ts
const isSuperAdmin = user?.role === "super_admin";
const isSchoolAdmin = user?.role === "admin";
const canEditPack = isSuperAdmin || !pack?.read_only;
const isGlobalPack = pack?.is_global_pack || pack?.source === "global";
```

- Show clear badges such as `Global`, `IREAD Platform`, or `Read only`.
- Disable hidden edit controls for school admins on global content.
- Keep normal school-owned packs editable for school admins.

### Super Admin Screens

- Global packs table/list with pagination and search.
- Create/edit global pack form.
- Global pack details page with tabs:
  - Books
  - Units
  - Sessions
  - Schools/Usage if available
- Platform book attach/detach UI.
- Unit CRUD UI.
- Session CRUD UI under units.
- Global teachers management UI.

### School Admin Screens

- Available global packs list with pagination and search.
- Add-to-school action.
- Joined global packs list.
- Remove-from-school action.
- Global pack details page in read-only mode.
- Student assignment UI reused from normal pack management.
- Ensure global packs appear in existing pack and session selectors where appropriate.

## Out Of Scope

- Do not implement the rule “student can join only one session per unit” unless the backend exposes a specific validation or route for it.
- Do not clone global pack data into editable local pack rows.
- Do not allow school admins to modify global pack books, units, sessions, PDFs, or headwords.
- Do not create a separate dashboard app for super admin.

## Acceptance Criteria

- Super admin can create a global pack, attach platform books, create units, create sessions, and manage global teachers.
- School admin can browse global packs, add one to their school, remove one from their school, and open details.
- School admin sees joined global packs in pack lists and session lists as read-only.
- School admin can assign students/readers to joined global packs using existing assignment flows.
- Pagination and search are supported on global-pack lists.
- All requests include cookies/session credentials.
- Existing school-owned pack, book, unit, session, and assignment workflows still work.
