# IRead Platform Books And School Instances Task

Use this separated task file for the next backend and admin dashboard update.

## Goal

Add a new IRead platform book flow.

Super admins can create and manage official IRead books. These books belong to the IRead platform, not to one school. A platform book can include:

- Book metadata: title, author, image, description, category, release date, page count.
- Story PDF file.
- Headwords or book text used by reader games.

School admins can add a platform book to their school as a ready-to-use book instance. This instance is not a real editable copy. It should keep using the super-admin master book, story PDF, and headwords exactly as the IRead platform provides them.

If the super admin later updates the platform book, PDF, or headwords, all schools using that platform book should automatically see the updated version.

## Important Product Rules

- There are two book types:
  - School book: created by a school admin, belongs to one school, editable by that school.
  - Platform book: created by a super admin, belongs to IRead, reusable by all schools, read-only for schools.
- School admins can add or remove a platform book from their own school.
- School admins cannot edit platform book metadata.
- School admins cannot edit platform book PDF stories.
- School admins cannot edit platform book headwords or `Book_text`.
- School admins can put a platform book inside their school packs.
- Readers should see platform books only when their selected school has added the platform book or has a pack that contains it.
- Reader PDF progress and completed status should keep working with the existing reader story progress routes.

## Backend Data Model

Prefer a link/instance table instead of physically duplicating books.

### Update `Book`

Add explicit ownership fields so platform books are not only inferred from `shcool_id IS NULL`.

Recommended fields:

```py
is_platform_book = db.Column(db.Boolean, nullable=False, default=False, index=True)
created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=True)
```

Rules:

- Platform book:
  - `Book.is_platform_book = True`
  - `Book.shcool_id = None`
  - `Book.created_by = current super admin id`
- School book:
  - `Book.is_platform_book = False`
  - `Book.shcool_id = current school id`
  - `Book.created_by = current school admin or teacher id`

Do not rely only on `Book.shcool_id = NULL`, because old data may already have null school IDs.

### Add `SchoolBookInstance`

Create a new model/table:

```py
class SchoolBookInstance(db.Model):
    __tablename__ = "school_book_instance"
    id = db.Column(db.Integer, primary_key=True)
    shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("shcool_id", "book_id", name="uq_school_platform_book"),
    )
```

Rules:

- `book_id` must point to a platform book.
- One school cannot create duplicate active instances for the same platform book.
- The instance only grants the school access to use the platform book.
- The instance must not copy metadata, PDF rows, or headwords into new rows.

### Update `BookStory`

Current story rows have `shcool_id` as required. Platform stories need to be allowed.

Recommended change:

```py
shcool_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=True, index=True)
```

Rules:

- School story:
  - `BookStory.shcool_id = current school id`
  - `BookStory.book_id` points to a school book.
- Platform story:
  - `BookStory.shcool_id = None`
  - `BookStory.book_id` points to a platform book.

Alternative: keep `shcool_id` required and add a dedicated platform school row, but this is less clean. Prefer nullable `shcool_id` for platform content.

### Headwords / Book Text

The current backend stores book words in `Book_text` using table name `bok_text`.

For this task:

- Use `Book_text.book_id` as the canonical headword source for the master platform book.
- Do not duplicate `Book_text` when a school creates an instance.
- Reader game route should read headwords from the master platform book ID.
- School admins must get 403 if they try to update `Book_text` for a platform book.

If a structured headword table is needed later, add it separately. For now, keep compatibility with `Book_text`.

## Backend Routes

### Super Admin Platform Book Routes

Add routes under `/admin/super`.

List platform books:

```http
GET /admin/super/platform-books?page=1&per_page=20&search=...
```

Create platform book with PDF and headwords:

```http
POST /admin/super/platform-books
Content-Type: multipart/form-data
```

Form fields:

```text
title
author
desc
category
release_date
page_number
img
headwords or text
file
story_title
story_description
```

Behavior:

- Create `Book` with `is_platform_book=True` and `shcool_id=None`.
- Create or update `Book_text` for the same book using `headwords` or `text`.
- Upload story PDF using the existing PDF upload validation.
- Create `BookStory` with `shcool_id=None`.
- Return full serialized platform book including story metadata and whether headwords exist.

Get one platform book:

```http
GET /admin/super/platform-books/<book_id>
```

Update platform book metadata:

```http
PUT /admin/super/platform-books/<book_id>
```

Update platform book headwords:

```http
PUT /admin/super/platform-books/<book_id>/headwords
```

Upload or replace platform book story PDF:

```http
POST /admin/super/platform-books/<book_id>/stories
```

Delete or deactivate platform book:

```http
DELETE /admin/super/platform-books/<book_id>
```

Recommended behavior for delete:

- Prefer soft delete/deactivate if any school instances exist.
- Do not break reader progress unexpectedly.

### School Admin Platform Book Instance Routes

List available IRead platform books:

```http
GET /admin/platform-books?page=1&per_page=20&search=...
```

Response should include:

```json
{
  "books": [
    {
      "id": 1,
      "title": "Book Title",
      "author": "Author",
      "source": "platform",
      "read_only": true,
      "already_added": false,
      "has_story_pdf": true,
      "has_headwords": true
    }
  ],
  "pagination": {}
}
```

Create a school instance:

```http
POST /admin/platform-books/<book_id>/instances
```

Behavior:

- Resolve the current school from `current_user`.
- Ensure `<book_id>` is an active platform book.
- Create `SchoolBookInstance`.
- Return the created instance and book summary.

List this school's platform book instances:

```http
GET /admin/school-platform-books?page=1&per_page=20&search=...
```

Remove a platform book from this school:

```http
DELETE /admin/school-platform-books/<instance_id>
```

Attach a platform book to a school pack:

```http
POST /admin/packs/<pack_id>/platform-books/<book_id>
```

Behavior:

- Pack must belong to current school.
- Book must be a platform book.
- School must already have a `SchoolBookInstance`, or the route can create one automatically.
- Add `Book_pack(pack_id=pack_id, book_id=book_id)`.
- Do not create a duplicated `Book` row.

Detach from a pack:

```http
DELETE /admin/packs/<pack_id>/platform-books/<book_id>
```

## Existing Route Updates

Update existing school admin book routes:

- `/admin/show_all_books`
- `/admin/get_book/<id>`
- `/admin/create_book`
- `/admin/update_book`
- `/admin/delete_book`
- `/admin/book_text`
- `/admin/books/<book_id>/stories`
- `/admin/stories/<story_id>`

Rules:

- School-owned books stay editable by the owning school.
- Platform books visible to the school should return `read_only: true`.
- Any school-admin update/delete attempt against a platform book must return 403.
- School admin `show_all_books` should include:
  - school-owned books
  - platform books added through `SchoolBookInstance`
  - platform books attached to the school's packs
- Serializer should include:

```json
{
  "source": "school | platform",
  "read_only": true,
  "school_id": 3,
  "is_platform_book": true,
  "instance_id": 10
}
```

## Reader Route Updates

Reader book and story access should support platform book instances.

Update reader access helpers so a reader can access a platform book when:

- the reader belongs to the selected school, and
- that school has an active `SchoolBookInstance` for the platform book, or
- the selected school has a pack containing that platform book.

Reader story PDF route should allow platform stories:

- `BookStory.shcool_id = None`
- `Book.is_platform_book = True`
- school access is checked through the school instance or school pack.

Reader headwords route:

```http
GET /reader/get_book_games/<book_id>
```

Should work for platform books without requiring a school-owned `Book_text` copy.

## Admin Dashboard Frontend Tasks

Add super admin UI:

- Platform books page.
- Create platform book form with:
  - metadata fields
  - PDF upload
  - headwords/book text textarea
- Edit platform book metadata.
- Replace/update story PDF.
- Update headwords.
- Show which schools are using each platform book.

Add school admin UI:

- IRead platform library page.
- Search and paginate platform books.
- Button: Add to my school.
- Show already added state.
- School books page should show both school books and platform books.
- Platform books must be visibly read-only.
- Hide or disable edit/delete/headword/PDF controls for platform books.
- Add platform book to pack flow.

## Permissions Checklist

- Only `super_admin` can create/update/delete platform books.
- Only `super_admin` can update platform story PDFs.
- Only `super_admin` can update platform headwords.
- School admins can only create/remove their own school instances.
- School admins can only attach platform books to packs from their own school.
- Teachers should not be able to edit platform book metadata, PDF, or headwords.
- Readers can only access platform books through a school they belong to.

## Migration Checklist

Create a new migration that:

- Adds `book.is_platform_book`.
- Adds `book.created_by`.
- Makes `book_story.shcool_id` nullable, if currently required.
- Creates `school_book_instance`.
- Adds useful indexes:
  - `book.is_platform_book`
  - `school_book_instance.shcool_id`
  - `school_book_instance.book_id`
  - unique `school_book_instance(shcool_id, book_id)`

Backfill decision:

- Do not blindly mark all old `Book.shcool_id IS NULL` rows as platform books unless those old rows are confirmed to be IRead catalog books.
- If old null-school books are the existing IRead catalog, use a controlled one-time SQL backfill:

```sql
UPDATE book
SET is_platform_book = 1
WHERE shcool_id IS NULL;
```

## Acceptance Criteria

- Super admin can create an IRead platform book with metadata, story PDF, and headwords.
- Super admin can update the platform book and all schools using it see the updated book.
- School admin can add a platform book to their school.
- School admin can attach a platform book to a school pack.
- School admin cannot edit platform book metadata, PDF, or headwords.
- School admin can still create and edit normal school-owned books.
- Reader can open the platform book story PDF from a joined school.
- Reader can continue from the last page and mark the story as completed.
- Reader games can load headwords for platform books.
- All list routes are paginated.
- No route leaks books across schools unless the user is `super_admin`.

## Suggested Implementation Order

1. Add model and migration changes.
2. Add serializer helpers for `source`, `read_only`, and `is_platform_book`.
3. Add super admin platform book CRUD and upload routes.
4. Add school admin platform library and instance routes.
5. Update existing school admin book routes to block platform edits.
6. Update reader access helpers for platform instances.
7. Update admin dashboard UI.
8. Run migration locally, test with one super admin, one school admin, and one reader.
9. Create a production migration based on the production Alembic head before deploying.
