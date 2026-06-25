# School Public Pages Feature Spec

Do not implement this feature until it is approved.

## Goal

Each school should have a public page on the IREAD platform. The page represents the school and lets students or school users create an account or sign in from that specific school page.

When a student/user belongs to multiple schools and signs in from a school public page, the app should send them directly to their reader dashboard using that school as the selected school context.

## Public URL

Recommended URL format:

```text
/schools/<school_slug>
```

Example:

```text
/schools/green-valley-school
```

Avoid using a root route like `/<school_name>` unless the frontend router is carefully checked, because it can conflict with existing pages.

## School Name And Slug Rules

- `school.name` must be unique.
- Add a unique public slug for each school.
- The slug should be generated from the school name by default.
- The slug must be URL-safe:
  - lowercase
  - spaces converted to `-`
  - no special unsafe URL characters
- The slug must be unique across all schools.
- If a school name changes, do not automatically break the public page URL unless the admin explicitly changes the slug.

Example:

```text
School name: Green Valley School
Slug: green-valley-school
Public page: /schools/green-valley-school
```

## Public Page Content

Each school page can contain between 1 and 3 sections.

Recommended content fields:

```json
{
  "school_id": 1,
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
      "content": "Short text for the first section.",
      "image": "https://..."
    }
  ]
}
```

Validation:

- Minimum sections: `1`
- Maximum sections: `3`
- Each section should have at least a title or content.
- Public page can be enabled/disabled by admin or super admin.

## Data Model Proposal

Keep the existing `shcool` table, but add uniqueness and public page support.

Option A: add columns to `shcool`:

```text
name unique
public_slug unique nullable initially
public_page_active boolean default true
logo nullable
cover_image nullable
headline nullable
description nullable
sections JSON nullable
created_at
updated_at
```

Option B: create a new table `school_public_page`:

```text
id
shcool_id unique foreign key
slug unique
active
logo
cover_image
headline
description
sections JSON
created_at
updated_at
```

Recommended: Option B, because public-page content stays separate from core school identity.

## Backend Routes

### Public Page Lookup

```http
GET /reader/schools/:slug/public-page
```

Returns public school page data.

This route must be public, no login required.

If not found or disabled:

```json
{
  "message": "School page not found"
}
```

### School Page Signup

```http
POST /reader/schools/:slug/register
```

This should behave like normal reader signup, but automatically joins the new user to the school represented by the public page.

Payload:

```json
{
  "username": "student",
  "email": "student@example.com",
  "password": "password"
}
```

Response should include:

```json
{
  "message": "User registered successfully",
  "school_id": 1,
  "school": "Green Valley School",
  "dashboard_url": "/dashboard?school_id=1"
}
```

### School Page Login

```http
POST /reader/schools/:slug/login
```

This should behave like normal login, but with school context.

Behavior:

- If user belongs to this school, log in and return dashboard URL for this school.
- If user belongs to multiple schools, still redirect to this school because they used this school page.
- If user does not belong to this school, return a clear error or optionally join them if the product decision allows open joining.

Recommended default:

```json
{
  "message": "You are not joined to this school"
}
```

Response on success:

```json
{
  "message": "Logged in successfully",
  "school_id": 1,
  "school": "Green Valley School",
  "dashboard_url": "/dashboard?school_id=1",
  "role": "reader"
}
```

### Optional: Set Selected School Context

Add a route if the frontend needs to switch selected school after login:

```http
POST /reader/select_school
```

Payload:

```json
{
  "school_id": 1
}
```

This can store selected school in session, but existing reader APIs should still accept `school_id` query/body for reliability.

## Admin Dashboard Routes

School admin and super admin should be able to manage public school pages.

### Get Current School Public Page

```http
GET /admin/school_public_page
```

For school admin, returns their school page.

### Update Current School Public Page

```http
PUT /admin/school_public_page
```

School admin can update:

- logo
- cover image
- headline
- description
- sections
- active status if allowed

School admin should not be able to change another school page.

### Super Admin School Page Management

Super admin can view and update any school page:

```http
GET /admin/super/schools/:schoolId/public-page
PUT /admin/super/schools/:schoolId/public-page
```

Super admin can also update slug/name if needed.

## Dashboard Frontend Tasks

Same admin dashboard app should support both school admin and super admin.

School admin:

- Add a `Public Page` settings screen.
- Show generated public page URL.
- Allow editing page content.
- Allow adding/removing/reordering sections, limited to 1-3 sections.
- Preview public page before saving if possible.

Super admin:

- Add public page fields inside school management.
- Allow checking slug uniqueness.
- Allow enabling/disabling public pages.
- Allow editing any school public page.

## Reader/Public Frontend Tasks

Create a public school page at:

```text
/schools/:slug
```

The page should:

- Load public page data by slug.
- Show school name, logo, cover, headline, description, and 1-3 sections.
- Include signup form.
- Include signin form.
- After signup, redirect to reader dashboard with this school selected.
- After signin, redirect to reader dashboard with this school selected.

Redirect target:

```text
/dashboard?school_id=<school_id>
```

All reader dashboard API calls should pass the selected school:

```http
GET /reader/dashboard?school_id=<school_id>
GET /reader/get_followed_pack_list?school_id=<school_id>
GET /reader/get_packs_by_school?school=<school_id>
```

## Multi-School Login Behavior

Important case:

A student belongs to:

- School A
- School B
- School C

The student opens:

```text
/schools/school-b
```

After login, they must go directly to the reader dashboard for School B.

They should not see a school chooser first.

## Security And Validation

- Public page lookup is public.
- Public page edit routes require login.
- School admin can only edit their own school page.
- Super admin can edit all school pages.
- Validate section count server-side.
- Validate slug uniqueness server-side.
- Prevent unsafe HTML in section content unless sanitized.
- Do not expose private school/admin data in the public page response.

## Migration Notes

Migration should:

- Add unique constraint/index for school name or enforce uniqueness safely.
- Add public page table or columns.
- Backfill slugs for existing schools.
- Handle duplicate existing school names before adding a unique constraint.

Duplicate school-name handling must be planned before applying migration on production.

Example strategy:

- Detect duplicates first.
- Fix duplicate names manually.
- Then apply unique index.

SQL check:

```sql
SELECT name, COUNT(*)
FROM shcool
GROUP BY name
HAVING COUNT(*) > 1;
```

## Acceptance Criteria

- Every school can have one public page.
- School public URL uses a unique slug.
- School name uniqueness is enforced.
- Page supports 1-3 content sections.
- New users signing up from a school page are automatically joined to that school.
- Existing users signing in from a school page are redirected to that school dashboard.
- Multi-school users bypass school selection when signing in from a specific school page.
- School admins can manage only their own public page.
- Super admin can manage all school public pages.
- Existing reader/admin login flows continue to work.
