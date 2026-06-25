# Codex Prompt: School Admin Public Page Frontend

You are working on the IREAD React admin dashboard. Implement the school-admin side of the new School Public Page feature.

Read the backend/product spec first if it exists in this repo:

```text
docs/school-public-pages-task.md
```

The same admin dashboard may also be used by super admin, but this task focuses only on the school admin experience.

## Goal

Add a dashboard screen where a school admin can manage the public page for their own school.

The public page represents the school on IREAD and lets students sign up or sign in from that school page. The page supports 1 to 3 content sections.

## Important Rules

- Do not change backend code.
- Use existing dashboard auth/session handling.
- All API requests must use `credentials: "include"`.
- School admin can only manage their own school public page.
- School admin should not manage other schools.
- Keep the existing dashboard layout, navigation, styling, and form patterns.
- Do not create a separate app.

## Expected Backend Routes

### Get Current School Public Page

```http
GET /admin/school_public_page
```

Expected response shape:

```json
{
  "public_page": {
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
        "content": "Short section content.",
        "image": "https://..."
      }
    ],
    "public_url": "/schools/green-valley-school"
  }
}
```

### Update Current School Public Page

```http
PUT /admin/school_public_page
```

Payload:

```json
{
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
  ]
}
```

Optional preview route:

```http
GET /reader/schools/:slug/public-page
```

Use it only if helpful for preview. The main school-admin edit screen should rely on `/admin/school_public_page`.

## UI Location

Add a dashboard navigation item:

```text
Settings > Public Page
```

or, if the dashboard already has school settings:

```text
School Settings > Public Page
```

## Screen Requirements

The page should include:

- School name display.
- Public page slug display.
- Public page URL display.
- Copy URL button.
- Open/Preview page button.
- Active/inactive toggle.
- Logo field.
- Cover image field.
- Headline field.
- Description field.
- Sections editor with 1 to 3 sections.
- Save button.
- Reset/cancel changes button.
- Loading state.
- Empty state if no page exists yet.
- Error state for failed API calls.
- Success toast/message after save.

## Section Editor

Each section should support:

- Title
- Content/body text
- Optional image URL
- Move up/down controls if there is more than one section
- Delete section button, disabled when only one section remains

Validation:

- Minimum sections: `1`
- Maximum sections: `3`
- At least one of `title` or `content` is required per section.
- Prevent adding a fourth section.
- Keep validation client-side before sending the save request.

## Public URL Behavior

Show the public URL clearly:

```text
/schools/<slug>
```

If the app has a configured frontend base URL, display the full URL:

```text
https://iread.education/schools/<slug>
```

If not, display the relative path.

The slug is unique and normally controlled by backend/super admin. For school admin, show it as read-only unless the backend explicitly allows editing it.

## UX Notes

- Keep the screen practical and admin-focused.
- Do not use a marketing landing page inside the dashboard.
- Do not add a big hero section in the dashboard edit screen.
- Use compact forms, clear labels, and predictable controls.
- Show a lightweight preview panel if it fits the existing dashboard style.
- If adding image fields, use the existing dashboard image upload or image URL pattern if one already exists.

## API Helper Example

Use the project’s existing API client if available. Otherwise follow this pattern:

```ts
const response = await fetch(`${API_URL}/admin/school_public_page`, {
  method: "GET",
  credentials: "include"
});
```

Save:

```ts
const response = await fetch(`${API_URL}/admin/school_public_page`, {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(payload)
});
```

## State Handling

Handle:

- Initial loading.
- Save loading.
- API errors.
- Validation errors.
- Dirty state when form changes.
- Refetch after successful save.

Do not lose unsaved changes accidentally when switching sections or editing images.

## Out Of Scope

- Do not implement the public reader-facing `/schools/:slug` page in this task.
- Do not implement signup/signin from the public page in this task.
- Do not implement super admin school public page management in this task.
- Do not change backend routes or database migrations.

## Acceptance Criteria

- School admin can open the Public Page settings screen.
- School admin can see their school name, slug, and public URL.
- School admin can copy/open the public URL.
- School admin can edit active status, logo, cover image, headline, description, and 1 to 3 sections.
- Client-side validation prevents invalid section count and empty sections.
- Save sends `PUT /admin/school_public_page` with the correct payload.
- All requests use `credentials: "include"`.
- Existing dashboard pages still work.
