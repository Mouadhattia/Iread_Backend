# Book Story PDF Reader Feature Spec

This is the separated planning/spec file for adding PDF stories to books.

## Goal

Each book can have one or more uploaded story PDFs. A school admin or teacher can upload a story PDF for a book. Readers can browse available stories, open a story, read it like a real book, flip pages left/right, zoom in/out, continue from the last page, and mark the story as completed.

This feature is sensitive because it touches file uploads, school permissions, reader access, and persistent reading progress.

## Existing Context

- `Book` now has `shcool_id`, so a book can belong directly to a school.
- A book can also belong to a school through `Book_pack -> Pack.shcool_id`.
- School admins are scoped through `User_shcool`.
- Reader access is school-aware.
- Current `Book_text` stores plain text for a book, but there is no PDF/story upload system yet.

## Backend Data Model

Add a new story model:

```py
class BookStory(db.Model):
    __tablename__ = "book_story"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False, index=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey("shcool.id"), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_url = db.Column(db.String(500), nullable=True)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    page_count = db.Column(db.Integer, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
```

Add reader progress:

```py
class ReaderStoryProgress(db.Model):
    __tablename__ = "reader_story_progress"
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey("book_story.id"), primary_key=True)
    current_page = db.Column(db.Integer, nullable=False, default=1)
    zoom = db.Column(db.Float, nullable=False, default=1)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_read_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
```

## File Storage

Store uploaded PDFs outside the code files:

```text
uploads/stories/<school_id>/<book_id>/<story_uuid>.pdf
```

Recommended config:

```py
STORY_UPLOAD_DIR = "uploads/stories"
MAX_STORY_UPLOAD_MB = 50
```

Rules:

- Accept only PDF files.
- Validate both extension and MIME type.
- Use `secure_filename`, but store with a generated UUID filename.
- Never trust the uploaded original filename for storage.
- Do not expose raw filesystem paths in public responses.
- Serve PDFs only through authenticated backend routes or signed/controlled URLs.

## Permission Rules

School admin:

- Can upload stories only for books in their current school.
- Can list, update, deactivate, and delete stories only in their current school.

Teacher:

- Can upload stories only if the teacher belongs to the same school as the book.
- If teacher permissions need to be narrower later, add a teacher-book or teacher-pack permission rule.

Reader:

- Can list/open stories only for books in a school they belong to.
- If the story is inside a paid/approved pack flow, require approved `Follow_pack` before access.
- Reader progress belongs only to the current reader.

Super admin:

- Can see all story metadata globally.
- Should not be required for normal school story upload.

## Admin/Teacher Backend Routes

Upload story:

```http
POST /admin/books/<book_id>/stories
Content-Type: multipart/form-data
```

Form data:

```text
file: story.pdf
title: Story title
description: optional
pack_id: optional, if frontend uploads from a pack context
```

Response:

```json
{
  "message": "Story uploaded successfully",
  "story": {
    "id": 1,
    "book_id": 10,
    "school_id": 3,
    "title": "Story title",
    "description": "optional",
    "page_count": 24,
    "active": true,
    "created_at": "2026-06-10T12:00:00"
  }
}
```

List stories for a book:

```http
GET /admin/books/<book_id>/stories?page=1&per_page=20
```

Update story metadata:

```http
PUT /admin/stories/<story_id>
```

Body:

```json
{
  "title": "Updated title",
  "description": "Updated description",
  "active": true
}
```

Delete/deactivate story:

```http
DELETE /admin/stories/<story_id>
```

Teacher aliases can be added if the teacher app needs separate route prefixes:

```http
POST /teacher/books/<book_id>/stories
GET /teacher/books/<book_id>/stories
PUT /teacher/stories/<story_id>
DELETE /teacher/stories/<story_id>
```

## Reader Backend Routes

List stories for one book:

```http
GET /reader/books/<book_id>/stories?school=<schoolId>
```

Response:

```json
{
  "stories": [
    {
      "id": 1,
      "book_id": 10,
      "title": "Story title",
      "description": "optional",
      "page_count": 24,
      "completed": false,
      "current_page": 5,
      "last_read_at": "2026-06-10T12:00:00"
    }
  ]
}
```

Get one story metadata:

```http
GET /reader/stories/<story_id>
```

Response:

```json
{
  "story": {
    "id": 1,
    "book_id": 10,
    "title": "Story title",
    "page_count": 24,
    "current_page": 5,
    "zoom": 1,
    "completed": false,
    "pdf_url": "/reader/stories/1/pdf"
  }
}
```

Serve PDF:

```http
GET /reader/stories/<story_id>/pdf
```

This route must check reader access before returning the PDF.

Update reading progress:

```http
PUT /reader/stories/<story_id>/progress
```

Body:

```json
{
  "current_page": 6,
  "zoom": 1.25
}
```

Mark completed:

```http
POST /reader/stories/<story_id>/complete
```

Response:

```json
{
  "message": "Story completed",
  "progress": {
    "story_id": 1,
    "current_page": 24,
    "completed": true,
    "completed_at": "2026-06-10T12:00:00"
  }
}
```

## Reader Frontend Behavior

Readers can:

- See a list of stories for a selected book.
- Open a story.
- Read the story like a real book.
- Flip pages left/right.
- Zoom in/out.
- Continue from the last page.
- Mark the story as completed.

Recommended frontend PDF library:

```text
react-pdf / pdf.js
```

Reader UI expectations:

- Show story title and progress.
- Render one or two pages depending on screen size.
- Left/right arrow buttons for page navigation.
- Keyboard support: left/right arrows.
- Zoom buttons and fit-width mode.
- Save progress after page changes, debounced.
- Save progress after zoom changes, debounced.
- On reopen, start at `current_page`.
- Show completed state when `completed=true`.

## Admin/Teacher Frontend Behavior

On each book detail page:

- Add a Stories section/tab.
- Show uploaded stories.
- Add upload PDF action.
- Validate file type before upload.
- Show upload progress.
- Show success/error messages.
- Allow edit metadata.
- Allow delete/deactivate.

Upload form:

```text
Title
Description
PDF file
Optional pack context
```

## Security Checklist

- Upload accepts PDF only.
- Limit max file size.
- Store files outside source code.
- Use generated filenames.
- Authenticate every PDF request.
- Check school access before upload/read.
- Do not allow readers to access stories from another school.
- Do not expose local file paths.
- Handle deleted/inactive story as 404.

## Migration Checklist

Create migration for:

- `book_story`
- `reader_story_progress`

No existing data backfill is required unless old PDFs already exist somewhere.

## Acceptance Criteria

Backend:

- School admin can upload a PDF story for a school book.
- Teacher can upload a PDF story for a school book if allowed by school membership.
- Reader can list stories for accessible books.
- Reader cannot access stories from another school.
- Reader can open the PDF through an authenticated route.
- Reader progress saves and reloads.
- Reader can mark story as completed.

Frontend:

- Admin/teacher book page has a story upload section.
- Reader book page has a story list.
- Reader story viewer supports page flip, zoom, resume, and completion.

## Suggested Implementation Order

1. Add models and migration.
2. Add secure file upload config and helpers.
3. Add school/admin upload routes.
4. Add reader list/pdf/progress routes.
5. Test access control with two schools.
6. Build admin/teacher story upload UI.
7. Build reader story list and PDF viewer.
8. Test mobile and desktop PDF reading.
