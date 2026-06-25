# Reader Frontend Multi-School Update Prompt

Use this prompt for the frontend implementation work on the reader side.

## Prompt

You are updating the IRead reader frontend for multi-school support. The backend now has school-aware admin routes and the core school schema exists: `Shcool`, `User_shcool`, and `Pack.shcool_id`. Reader-side frontend work should make every reader flow operate inside an active school context.

### Main Goal

Update the reader experience so users browse packs, view sessions/books, follow packs, register for sessions, and see dashboard data only for the selected or assigned school.

### Backend Contract To Use

Use `GET /reader/user_authenticated` on app startup with credentials/cookies enabled.

Expected authenticated admin shape:

```json
{
  "is_authenticated": true,
  "role": "admin",
  "id": 1,
  "school_id": 1,
  "school": "IRead"
}
```

Expected authenticated reader/teacher/assistant shape:

```json
{
  "is_authenticated": true,
  "role": "reader",
  "id": 10,
  "schools": [
    { "id": 1, "name": "IRead" }
  ]
}
```

For school pack browsing, use:

```http
GET /reader/get_packs_by_school?school=<activeSchoolId>&all=0&age=<optional>&title=<optional>
```

For school pack detail, including books inside the pack, use:

```http
GET /reader/get_pack_details?school=<activeSchoolId>&id=<packId>
```

The response includes both `books` and `books_in_pack` arrays for compatibility.

If a screen only needs books inside the pack, use:

```http
GET /reader/get_books_from_pack?school=<activeSchoolId>&id=<packId>
```

For joining another school from reader settings, use:

```http
POST /reader/join_school_by_invitation
```

Request body:

```json
{
  "code": "SCHOOLCODE"
}
```

Successful response:

```json
{
  "message": "School joined successfully",
  "school": { "id": 2, "name": "School Name" },
  "schools": [
    { "id": 1, "name": "IRead" },
    { "id": 2, "name": "School Name" }
  ]
}
```

After redeeming an invitation code, refresh the active school state from the returned `schools` array or from `GET /reader/user_authenticated`.

For direct school discovery and joining without an invitation code, use:

```http
GET /reader/get_all_schools
```

Response:

```json
{
  "schools": [
    { "id": 1, "name": "IRead", "joined": true },
    { "id": 2, "name": "School Name", "joined": false }
  ]
}
```

To join one school:

```http
POST /reader/join_school
```

```json
{
  "school_id": 2
}
```

To join multiple schools in one request:

```json
{
  "school_ids": [2, 3, 4]
}
```

After joining, refresh the active school state from the returned `schools` array or from `GET /reader/user_authenticated`.

Use `all=0` for public/reader browsing. Do not expose `all=1` to guests. Treat `all=1` as admin/internal until backend permission checks are confirmed.

For reader self-service actions, prefer endpoints that use the logged-in user:

- `POST /reader/follow_pack`
- `POST /reader/register_session`
- `POST /reader/cancel_register_session`
- `GET /reader/get_followed_pack_list?school=<activeSchoolId>`
- `GET /reader/get_unfollowed_books?school=<activeSchoolId>`
- `POST /reader/unfollowed_pack`
- `GET /reader/dashboard?school=<activeSchoolId>`
- `GET /reader/my__profile`
- `POST /reader/set_profile`

Avoid using these reader helper endpoints from the public reader UI because they accept raw `user_id` and still need backend cleanup:

- `POST /reader/add_user_to__session`
- `POST /reader/remove_user_from_session`
- `POST /reader/link_code`

Game result endpoints still accept `user_id` and leaderboards are currently scoped by `book_id`, not school. For now, only send the authenticated user's ID from `/reader/user_authenticated`; never accept `user_id` from the URL or user input. Keep active school, pack, and session context in client state so the backend can be upgraded later.

### Frontend State Requirements

Create a single active school state source:

- `activeSchoolId`
- `activeSchoolName`
- `availableSchools`
- `isSchoolResolved`

Resolution rules:

1. On app startup, call `/reader/user_authenticated`.
2. If the user is authenticated and response has `school_id`, set it as the active school.
3. If the user is authenticated and response has `schools`, use the first school by default.
4. If more than one school exists, show a school selector/switcher.
5. Persist the active school in local storage or session storage.
6. If the persisted school is not in the returned `schools` array, reset it.
7. For guests, resolve school from route, subdomain, config, or a public school selector. Do not call admin school endpoints from the reader UI because admin routes now require admin auth.

### Routing And Screens

Reader pages that must use active school:

- Public pack listing
- Reader pack listing
- Pack detail
- Books inside pack
- Sessions for a pack/book
- Follow pack with code
- Session registration
- Reader dashboard cards/statistics
- Game entry points and leaderboards

Add a small school indicator in the reader shell/header so the user can see which school context is active.

### API Usage Rules

All reader API requests must use credentials:

```js
fetch(url, {
  credentials: "include",
  headers: { "Content-Type": "application/json" }
})
```

For pack listing, always include the selected school:

```js
const url = `${API_URL}/reader/get_packs_by_school?school=${activeSchoolId}&all=0`;
```

For followed packs, unfollowed books, and dashboard sessions, always include the selected school:

```js
fetch(`${API_URL}/reader/get_followed_pack_list?school=${activeSchoolId}`, { credentials: "include" });
fetch(`${API_URL}/reader/get_unfollowed_books?school=${activeSchoolId}`, { credentials: "include" });
fetch(`${API_URL}/reader/dashboard?school=${activeSchoolId}`, { credentials: "include" });
```

If the logged-in reader belongs to multiple schools and no school is sent, these endpoints return `400` with `school_id is required`.

Do not use these global/public pack endpoints for school-specific reader pages unless the backend is updated to accept and enforce school:

- `/main/show_all_pack`
- `/main/get_pack_details`
- `/main/get_books_from_pack`

If legacy code still calls those endpoints, replace it with the school-aware reader calls above.

### UX Behavior

Handle responses this way:

- `401`: redirect to login or show signed-out state.
- `403`: show "No school access" or "You do not have access to this school".
- `404`: treat as not found or not available in this school.
- `500`: show a retry state and log details for development.

When switching schools:

1. Clear currently loaded packs/books/sessions.
2. Refetch packs for the new school.
3. Clear selected pack/session if it does not belong to the new school.
4. Keep the user logged in.

### Registration/Login Notes

The backend keeps the existing self-registration behavior, so regular signup still works without school selection. It also now accepts an optional school invitation code for signup and Google signup.

Optional registration payload:

```json
{
  "username": "reader name",
  "email": "reader@example.com",
  "password": "secret",
  "invitation_code": "SCHOOLCODE"
}
```

Do not send `school_id` during reader signup. A reader joins schools through invitation codes or through admin-created accounts.

### QA Checklist

- A guest can only see public packs for the selected school.
- A logged-in reader sees their assigned school from `/reader/user_authenticated`.
- If a reader belongs to multiple schools, switching school refetches packs and resets stale selected pack/session.
- A logged-in reader can redeem a school invitation code from settings and then sees the new school in the selector.
- A logged-in reader can browse all schools and join one or multiple schools directly from settings.
- Reader pack listing calls `/reader/get_packs_by_school` with `school=<activeSchoolId>`.
- Followed packs, unfollowed books, and dashboard sessions call their reader endpoints with `school=<activeSchoolId>`.
- The UI does not call admin school endpoints for public reader pages.
- The UI does not send arbitrary `user_id` for reader session actions.
- Pack join with code handles wrong-code, used-code, and wrong-pack responses.
- Session registration handles full session and missing approved pack responses.
- Game results use the authenticated user ID only.
- 401/403/404 states are visible and understandable.

### Important Backend Follow-Ups To Track

- Decide whether regular self-registration should keep the default `IRead` school membership after an invitation-code signup.
- Replace hard-coded `IRead` in reader account creation if the default school should be removed later.
- Move raw `user_id` helper endpoints to admin or protect them.
- Add school/pack/session scope to game results and leaderboards.
- Add a public school discovery endpoint if the frontend cannot resolve school from route/subdomain/config.
