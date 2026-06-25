# Synchronized Audio Books Backend Routes

Backend phase implemented for Synchronized Audio Books.

## Migration

New migration:

```text
migrations/versions/d9a4c1b7e8f2_synchronized_audiobooks.py
```

Apply with:

```bash
flask db upgrade
```

## Models

New models:

```text
models/audio_book.py
```

Tables:

- `audio_book`
- `audio_book_page`
- `audio_book_progress`

## Upload Config

New config values:

```text
AUDIOBOOK_UPLOAD_DIR
MAX_AUDIOBOOK_IMAGE_UPLOAD_MB
MAX_AUDIOBOOK_AUDIO_UPLOAD_MB
AUDIOBOOK_ALIGNMENT_MODEL
AUDIOBOOK_ALIGNMENT_DEVICE
```

## Admin Routes

Prefix: `/admin`

```text
POST   /admin/audio-books
GET    /admin/audio-books?page=1&per_page=20
GET    /admin/audio-books/<book_id>
PUT    /admin/audio-books/<book_id>
DELETE /admin/audio-books/<book_id>
GET    /admin/audio-books/<book_id>/cover

POST   /admin/audio-books/<book_id>/pages
PUT    /admin/audio-books/<book_id>/pages/<page_id>
DELETE /admin/audio-books/<book_id>/pages/<page_id>
PUT    /admin/audio-books/<book_id>/pages/reorder
PUT    /admin/audio-books/<book_id>/pages/<page_id>/alignment
POST   /admin/audio-books/<book_id>/pages/<page_id>/generate-alignment
POST   /admin/audio-books/<book_id>/pages/<page_id>/approve
GET    /admin/audio-books/<book_id>/pages/<page_id>/image
GET    /admin/audio-books/<book_id>/pages/<page_id>/audio

POST   /admin/audio-books/<book_id>/publish
POST   /admin/audio-books/<book_id>/unpublish
```

Super admin can manage all audiobooks. School admin can manage audiobooks for the current school.

## Teacher Routes

Prefix: `/teacher`

```text
POST   /teacher/audio-books
GET    /teacher/audio-books?page=1&per_page=20
GET    /teacher/audio-books/<book_id>
PUT    /teacher/audio-books/<book_id>
DELETE /teacher/audio-books/<book_id>
GET    /teacher/audio-books/<book_id>/cover

POST   /teacher/audio-books/<book_id>/pages
PUT    /teacher/audio-books/<book_id>/pages/<page_id>
DELETE /teacher/audio-books/<book_id>/pages/<page_id>
PUT    /teacher/audio-books/<book_id>/pages/reorder
PUT    /teacher/audio-books/<book_id>/pages/<page_id>/alignment
POST   /teacher/audio-books/<book_id>/pages/<page_id>/generate-alignment
POST   /teacher/audio-books/<book_id>/pages/<page_id>/approve
GET    /teacher/audio-books/<book_id>/pages/<page_id>/image
GET    /teacher/audio-books/<book_id>/pages/<page_id>/audio

POST   /teacher/audio-books/<book_id>/publish
POST   /teacher/audio-books/<book_id>/unpublish
```

Teacher can manage only audiobooks they created.

## Reader Routes

Prefix: `/reader`

```text
GET      /reader/audio-books?page=1&per_page=20
GET      /reader/audio-books/<book_id>
GET      /reader/audio-books/<book_id>/cover
GET      /reader/audio-books/<book_id>/pages/<page_number>
GET      /reader/audio-books/<book_id>/pages/<page_number>/image
GET      /reader/audio-books/<book_id>/pages/<page_number>/audio
POST/PUT /reader/audio-books/<book_id>/progress
```

Reader routes return only published audiobooks and approved pages.

## Create Page Multipart Fields

Required:

```text
page_number
official_text
image
audio
```

Optional:

```text
language
audio_duration_ms
alignment_json
similarity
```

Accepted image types:

```text
jpg, jpeg, png, webp
```

Accepted audio types:

```text
mp3, wav, m4a, webm, ogg
```

## Alignment

Alignment JSON is validated server-side before save, approval, and publish.

Model alignment routes use `whisper-timestamped` to generate real word-level
timestamps from the uploaded audio, then align the recognized transcript back
to the official page text. Official words that the model cannot match are
returned as `not-spoken` and flagged in `review.unmatchedOfficialWords`.
Extra spoken words are flagged in `review.extraTranscribedWords`.

Page approval requires:

- image file
- audio file
- official text
- valid alignment JSON

Publishing requires:

- at least one page
- every active page approved
- every active page has image, audio, official text, and valid alignment JSON
