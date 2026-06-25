# Codex Prompt: Reader Public School Page Frontend

You are working on the IREAD reader React frontend. Implement the public school page feature.

This task is only for the reader/public frontend side.

## Goal

Create a public page for each school at:

```text
/schools/:slug
```

The page displays the school information from the backend and allows users to sign up or sign in from that specific school page.

If a user belongs to multiple schools and signs in from a school page, they must go directly to the reader dashboard for that school.

## Important Rules

- Do not change backend code.
- Use the existing frontend routing, auth, API helpers, form patterns, and styling.
- All API requests that create/login/select a session must use `credentials: "include"`.
- The public page lookup does not require login.
- Do not add a school chooser after login from this page.
- Redirect directly to the dashboard with the selected school.

## Public Route

Add a reader/public frontend route:

```text
/schools/:slug
```

Examples:

```text
/schools/iread
/schools/green-valley-school
```

## Backend APIs

### Get Public School Page

```http
GET /reader/schools/:slug/public-page
```

This route is public.

Expected response:

```json
{
  "public_page": {
    "school_id": 1,
    "shcool_id": 1,
    "school_name": "Green Valley School",
    "slug": "green-valley-school",
    "active": true,
    "logo": "https://...",
    "cover_image": "https://...",
    "headline": "Read with Green Valley School",
    "description": "Welcome to our IREAD reading space.",
    "sections": [
      {
        "title": "Our Reading Program",
        "content": "Short section content.",
        "image": "https://..."
      }
    ],
    "public_url": "/schools/green-valley-school",
    "full_public_url": "https://iread.education/schools/green-valley-school"
  }
}
```

If not found or inactive:

```json
{
  "message": "School page not found"
}
```

### Signup From School Page

```http
POST /reader/schools/:slug/register
```

Payload:

```json
{
  "username": "student",
  "email": "student@example.com",
  "password": "password"
}
```

Expected response:

```json
{
  "message": "Your account has been successfully created. Please verify your emailbox to confirm your account",
  "user": {
    "username": "student",
    "email": "student@example.com"
  },
  "school_id": 1,
  "school": "Green Valley School",
  "dashboard_url": "/dashboard?school_id=1"
}
```

After successful signup, show the backend message and guide the user to verify email. If the existing app logs users in after signup, follow existing behavior, but do not assume this route logs in because backend currently requires email confirmation.

### Login From School Page

```http
POST /reader/schools/:slug/login
```

Payload:

```json
{
  "email": "student@example.com",
  "password": "password"
}
```

Expected response:

```json
{
  "message": "Your are logged in succesfully",
  "role": "reader",
  "school_id": 1,
  "school": "Green Valley School",
  "dashboard_url": "/dashboard?school_id=1"
}
```

On success, redirect to:

```text
/dashboard?school_id=<school_id>
```

Use `dashboard_url` from backend if available.

### Optional Select School

If the app needs to set selected school context separately:

```http
POST /reader/select_school
```

Payload:

```json
{
  "school_id": 1
}
```

This route requires login and stores the selected school in the backend session.

## Page Layout

The page should show:

- School logo if available.
- School cover image if available.
- School name.
- Headline.
- Description.
- 1 to 3 content sections.
- Signup form.
- Login form.

Use tabs, segmented control, or a compact switch between:

```text
Sign in
Create account
```

Do not show admin-only controls.

## Form Requirements

### Login Form

Fields:

- Email
- Password

On submit:

```http
POST /reader/schools/:slug/login
```

Use:

```ts
credentials: "include"
```

On success:

```ts
navigate(response.dashboard_url || `/dashboard?school_id=${response.school_id}`)
```

### Signup Form

Fields:

- Username
- Email
- Password
- Confirm password if the current app normally uses it

Validate:

- Required fields.
- Passwords match if confirm password exists.
- Show backend error messages.

On submit:

```http
POST /reader/schools/:slug/register
```

Use:

```ts
credentials: "include"
```

On success:

- Show the backend success message.
- Keep the user on the page or move them to the existing email-verification screen if the app has one.

## Dashboard School Context

When redirecting from the school page, make sure the dashboard uses the selected school:

```text
/dashboard?school_id=<school_id>
```

All reader dashboard calls should pass this `school_id` when available:

```http
GET /reader/dashboard?school_id=<school_id>
GET /reader/get_followed_pack_list?school_id=<school_id>
GET /reader/get_unfollowed_books?school_id=<school_id>
```

If the app stores selected school in local state/context/localStorage, update it after login using the returned `school_id`.

## Multi-School Behavior

Important case:

A user belongs to multiple schools:

- School A
- School B
- School C

They open:

```text
/schools/school-b
```

They sign in successfully.

They must go directly to:

```text
/dashboard?school_id=<school_b_id>
```

Do not show a school chooser first.

## Error States

Handle:

- Page loading.
- Page not found or inactive.
- API error.
- Login invalid credentials.
- Account not confirmed.
- Account not approved.
- User is not joined to this school.
- Signup email already used.

For this backend message:

```text
You are not joined to this school
```

show a clear message. Do not redirect.

## UX Notes

- This is a public school-facing page, so it should feel polished and trustworthy.
- Use the school cover image or logo as the main visual signal if available.
- Keep the forms easy to find.
- Make the page responsive on mobile and desktop.
- Avoid showing internal API names like `shcool_id`.

## Out Of Scope

- Do not build school-admin page editing in this task.
- Do not build super-admin page editing in this task.
- Do not change backend routes.
- Do not add a new school chooser after login from this route.

## Acceptance Criteria

- `/schools/:slug` loads and renders public school page data.
- Inactive/missing school pages show a clean not-found state.
- Login from the school page calls `POST /reader/schools/:slug/login`.
- Successful login redirects directly to the reader dashboard with `school_id`.
- Signup from the school page calls `POST /reader/schools/:slug/register`.
- Signup success shows email verification guidance.
- Multi-school users do not see a school chooser when logging in from a school page.
- All session/auth requests use `credentials: "include"`.
- Existing reader login/signup pages still work.
