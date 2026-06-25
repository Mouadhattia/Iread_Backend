# Admin Dashboard Frontend Prompt: IRead Platform Books

Copy this prompt into Codex inside the React admin dashboard app.

## Prompt

You are updating the IRead React admin dashboard to support the new backend platform-book system.

The backend is already updated. Do not change backend code. Update only the React admin frontend, API client, routing, state, forms, tables, and UI.

Every request must include session cookies:

```js
fetch(url, {
  credentials: "include"
});
```

For JSON requests:

```js
fetch(url, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data)
});
```

For PDF uploads, use `FormData` and do not manually set `Content-Type`:

```js
const formData = new FormData();
formData.append("file", pdfFile);

fetch(url, {
  method: "POST",
  credentials: "include",
  body: formData
});
```

The PDF field name must be exactly:

```text
file
```

## Main Goal

Add dashboard support for two book flows:

- `super_admin`: creates and manages official IRead platform books.
- `admin`: normal school admin can add IRead platform books to their school and packs, but cannot edit the platform book, PDF, or headwords.

Platform books are master books owned by IRead. Schools do not get duplicated book rows. Schools create a school instance/link to use the platform book.

## Auth

Use the existing auth endpoint:

```http
GET /reader/user_authenticated
```

Use `role` to decide navigation:

- `super_admin`: show platform book management.
- `admin`: show IRead platform library and read-only platform books inside school book/pack flows.

## Super Admin UI

Add a new navigation item:

```text
IRead Platform Books
```

This page should allow super admins to:

- List platform books.
- Search platform books.
- Create platform book with metadata, PDF story, and headwords.
- View platform book details.
- Edit platform book metadata.
- Update platform book headwords.
- Upload/add a new story PDF.
- Deactivate/delete platform book.
- See schools using each platform book.

### Super Admin Endpoints

List platform books:

```http
GET /admin/super/platform-books?page=1&per_page=20&search=...
```

Create platform book:

```http
POST /admin/super/platform-books
Content-Type: multipart/form-data
```

FormData fields:

```text
title
author
desc
category
release_date
page_number
img
headwords
file
story_title
story_description
```

Required fields:

```text
title
author
headwords or text
file
```

Get one platform book:

```http
GET /admin/super/platform-books/:bookId
```

Update metadata:

```http
PUT /admin/super/platform-books/:bookId
Content-Type: application/json
```

Update headwords:

```http
PUT /admin/super/platform-books/:bookId/headwords
Content-Type: application/json
```

Body:

```json
{
  "headwords": "word1 word2 word3"
}
```

Upload/add platform story PDF:

```http
POST /admin/super/platform-books/:bookId/stories
Content-Type: multipart/form-data
```

FormData fields:

```text
file
title
description
```

Delete/deactivate platform book:

```http
DELETE /admin/super/platform-books/:bookId
```

If the book is already used by schools/readers, the backend may deactivate it instead of hard deleting.

## School Admin UI

Add a new navigation item:

```text
IRead Library
```

This page should allow school admins to:

- Browse official IRead platform books.
- Search and paginate.
- Add a platform book to their school.
- See already-added state.
- Attach platform books to their own packs.
- Remove a platform book from their school.

School admins cannot edit platform books. Hide or disable:

- Edit metadata button.
- Delete master book button.
- PDF upload/replace controls.
- Headwords edit controls.

### School Admin Endpoints

List available platform books:

```http
GET /admin/platform-books?page=1&per_page=20&search=...
```

Create school instance:

```http
POST /admin/platform-books/:bookId/instances
```

Remove platform book from this school by book id:

```http
DELETE /admin/platform-books/:bookId/instances
```

List this school's platform book instances:

```http
GET /admin/school-platform-books?page=1&per_page=20&search=...
```

List this school's platform books only, without wrapping them as instances:

```http
GET /admin/school-platform-books/books?page=1&per_page=20&search=...
```

Remove platform book from this school:

```http
DELETE /admin/school-platform-books/:instanceId
```

Attach platform book to pack:

```http
POST /admin/packs/:packId/platform-books/:bookId
```

Detach platform book from pack:

```http
DELETE /admin/packs/:packId/platform-books/:bookId
```

## Existing Book Pages

Update existing school admin book pages that call:

```http
GET /admin/show_all_books
GET /admin/get_book/:bookId
PUT /admin/update_book
POST /admin/delete_book
GET /admin/book_text/:bookId
PUT /admin/book_text/:bookId
GET /admin/books/:bookId/stories
POST /admin/books/:bookId/stories
```

Backend now returns platform metadata on book objects:

```json
{
  "id": 1,
  "title": "Book Title",
  "author": "Author",
  "school_id": 3,
  "owner_school_id": null,
  "is_platform_book": true,
  "source": "platform",
  "read_only": true,
  "instance_id": 10,
  "has_story_pdf": true,
  "has_headwords": true,
  "pack_ids": [4, 5]
}
```

Use these fields:

- If `read_only === true`, disable edit/delete/headword/PDF mutation controls.
- If `source === "platform"`, show it as an IRead platform book.
- If `instance_id` exists, it is already added to the school.
- Keep normal school books fully editable.

## Pack Flow

When adding books to a pack:

- Normal school books can keep using the existing add-to-pack route.
- Platform books should use:

```http
POST /admin/packs/:packId/platform-books/:bookId
```

When removing platform books from a pack, use:

```http
DELETE /admin/packs/:packId/platform-books/:bookId
```

Do not send platform books to old book update routes.

## UI Behavior

Super admin:

- Platform book rows should have edit, headwords, PDF/story, schools usage, and delete/deactivate actions.
- Create form must support metadata, PDF file input, and large headwords textarea.
- Upload progress/loading state should be shown during PDF upload.

School admin:

- IRead Library cards/table rows should show Add to my school or Added.
- School book list should include platform books and school books together.
- Platform books must clearly look read-only.
- Pack editor should let the school admin attach added platform books to packs.

## Error Handling

Show backend `message` or `error` from JSON responses.

Common expected errors:

```text
IRead platform books are read-only for school admins
IRead platform story PDFs are read-only for school admins
IRead platform headwords are read-only for school admins
Platform book not found
Platform book already exists in this pack
```

## Acceptance Criteria

- Super admin can create a platform book with PDF and headwords.
- Super admin can update metadata and headwords.
- Super admin can upload another PDF story for the platform book.
- School admin can browse IRead Library.
- School admin can add platform book to their school.
- School admin can remove platform book from their school by `bookId`.
- School admin can fetch only platform books already added to their school.
- School admin can attach platform book to one of their packs.
- School admin sees platform books in existing books page.
- School admin cannot edit platform metadata, PDF, or headwords.
- Existing normal school book create/edit/delete still works.
- All lists use pagination from backend responses.
