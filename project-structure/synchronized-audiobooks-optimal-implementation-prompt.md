# Synchronized Audio Books - Optimal Implementation Prompt

Use this prompt with Codex to implement the Synchronized Audio Books feature. This feature is large and sensitive, so implement it in phases. Do not skip the inspection phase.

## Context

You are working on the iRead reading platform.

Backend:

- Flask app
- Flask-SQLAlchemy through `extensions.db`
- Flask-Login auth through `current_user`
- Existing blueprints:
  - `apps/admin/routes.py` with prefix `/admin`
  - `apps/teacher/routes.py` with prefix `/teacher`
  - `apps/reader/routes.py` with prefix `/reader`
- Existing models live in `models/`
- Existing Alembic migrations live in `migrations/versions/`
- Existing uploads pattern is used for story PDFs:
  - `models/book_story.py`
  - `models/reader_story_progress.py`
  - `ConfigClass.STORY_UPLOAD_DIR`
- Existing school ownership field is misspelled as `shcool_id`. Keep compatibility with existing naming unless a migration safely introduces a new field.
- Roles include `reader`, `teacher`, `admin`, and `super_admin`.
- `super_admin` manages platform/global content.
- School admins are `admin` users associated with a school.

Frontend apps may be in separate repositories:

- Admin/school dashboard React app
- Reader React app
- The backend repo may only contain backend code and task docs. If a frontend repo is not present, create/update prompt files for that frontend instead of inventing files in the backend.

## Feature Goal

Implement Synchronized Audio Books.

Admins and teachers can create audiobooks page by page. Each page contains:

- page image
- official page text
- narration audio
- synchronized word timestamp JSON

Readers can open published audiobooks and listen while the official text is highlighted word by word.

## Critical Architecture Rules

Do not run Whisper, speech-to-text, or any AI transcription on the backend.

The backend only stores:

- audiobook metadata
- page image file
- page audio file
- official text
- final alignment JSON
- statuses and progress

The admin/teacher browser handles:

- AI model download
- AI model cache
- audio decoding
- speech-to-text transcription
- transcript-to-official-text alignment
- preview
- manual correction
- local draft storage

Readers must never download the AI model. Reader APIs return only published image/audio/text/alignment data.

The official teacher text is always the source of truth. AI output is used only to generate timing data. Never silently rewrite official text with the transcript.

## Implementation Strategy

Implement this as incremental phases. After each phase:

- run available backend tests
- run frontend type checks/build/tests when a frontend repo is present
- summarize routes, models, and remaining work

Do not attempt to finish the whole feature in one risky pass if the app is split across repos.

## Phase 0 - Inspect And Produce A Concrete Plan

Before editing:

1. Inspect backend models, blueprints, auth helpers, role checks, upload helpers, migration style, tests, and existing story PDF routes.
2. Inspect admin dashboard structure if present.
3. Inspect reader frontend structure if present.
4. Confirm how teachers are linked to schools.
5. Confirm how school admins get current school context.
6. Confirm existing file upload URL generation.

Then produce a short implementation plan that names the files to edit.

## Phase 1 - Backend Data Model And API

Create backend support first.

### Models

Add models following existing style:

`AudioBook`

- `id`
- `title`
- `description`
- `cover_image_url`
- `language`
- `level` or `category` only if existing app conventions support it
- `status`: `draft`, `published`, `archived` if supported
- `shcool_id`: nullable for platform/global audiobooks, set for school audiobooks
- `created_by_id`
- `created_by_role`
- `published_at`
- `active`
- `created_at`
- `updated_at`

`AudioBookPage`

- `id`
- `audio_book_id`
- `page_number`
- `image_url`
- `image_path`
- `audio_url`
- `audio_path`
- `official_text`
- `language`
- `audio_duration_ms`
- `alignment_json`
- `alignment_status`: `draft`, `queued-local`, `processing-local`, `review-required`, `ready`, `approved`, `failed`
- `similarity`
- `created_at`
- `updated_at`

`AudioBookProgress`

- `user_id`
- `audio_book_id`
- `current_page_number`
- `current_time_ms`
- `completed`
- `completed_at`
- `updated_at`

Use a JSON column if MySQL setup supports it; otherwise use text for `alignment_json` and serialize/deserialize safely.

Create an Alembic migration.

### Upload Config

Reuse existing upload conventions and add config values:

- `AUDIOBOOK_UPLOAD_DIR`
- `MAX_AUDIOBOOK_IMAGE_UPLOAD_MB`, default 10
- `MAX_AUDIOBOOK_AUDIO_UPLOAD_MB`, default 50

Accepted image MIME/types:

- jpg
- jpeg
- png
- webp

Accepted audio MIME/types:

- mp3
- wav
- m4a
- webm
- ogg when supported

### Backend Validation

Add reusable helpers for:

- role permission checks
- school scope checks
- teacher ownership checks
- file extension and MIME validation
- file size validation
- alignment JSON validation
- page status transitions
- publish eligibility

Validate alignment JSON server-side. At minimum:

- `version` exists
- `officialText` is a string
- `words` is an ordered array
- each word has `index`, `text`, `startMs`, `endMs`, `status`
- `startMs >= 0`
- `endMs >= startMs`
- `endMs <= audioDurationMs` when audio duration is known
- status is one of `matched`, `interpolated`, `unmatched`, `manually-edited`, `not-spoken`

Do not trust frontend validation.

### Admin And Teacher Routes

Use existing route prefixes. Prefer these endpoints unless existing naming style requires a small adjustment.

Admin/school-admin:

- `POST /admin/audio-books`
- `GET /admin/audio-books`
- `GET /admin/audio-books/<book_id>`
- `PUT /admin/audio-books/<book_id>`
- `DELETE /admin/audio-books/<book_id>`
- `POST /admin/audio-books/<book_id>/pages`
- `PUT /admin/audio-books/<book_id>/pages/<page_id>`
- `DELETE /admin/audio-books/<book_id>/pages/<page_id>`
- `PUT /admin/audio-books/<book_id>/pages/reorder`
- `PUT /admin/audio-books/<book_id>/pages/<page_id>/alignment`
- `POST /admin/audio-books/<book_id>/pages/<page_id>/approve`
- `POST /admin/audio-books/<book_id>/publish`
- `POST /admin/audio-books/<book_id>/unpublish`

Teacher:

- Mirror the page/book routes under `/teacher/audio-books...` if the current dashboard calls teacher APIs separately.
- Teacher can manage only audiobooks they created, unless existing permission logic says otherwise.
- Teacher cannot edit another teacher's audiobook.

Super admin:

- Can manage all audiobooks.
- Can create platform/global audiobooks with `shcool_id = NULL`.
- Keep list endpoints paginated.

Reader:

- `GET /reader/audio-books`
- `GET /reader/audio-books/<book_id>`
- `GET /reader/audio-books/<book_id>/pages/<page_number>`
- `POST /reader/audio-books/<book_id>/progress`
- `POST /reader/audio-books/<book_id>/complete` if consistent with existing progress APIs

Reader APIs must only return published audiobooks and approved pages. They must not return drafts, unapproved pages, failed pages, or creator-only metadata.

### Publishing Rules

Backend must enforce:

- cannot publish with zero pages
- cannot publish when any page is not approved
- cannot publish when any page is missing image, audio, official text, or valid alignment JSON
- only admin/super_admin/owner teacher can publish
- unpublish returns book to draft or unpublished state based on existing status conventions

## Phase 2 - Backend Tests

Add tests where the project has an existing test pattern. Cover:

- create audiobook
- create page
- save valid alignment JSON
- reject invalid alignment JSON
- approve page
- reject publish when a page is not approved
- publish when all pages are approved
- reader cannot see draft audiobook
- reader can see published audiobook
- teacher cannot edit another teacher's audiobook
- super_admin can manage all audiobooks

## Phase 3 - Admin/Teacher Frontend

If the admin dashboard repo is present, implement. If it is not present, create a frontend task prompt file.

Add navigation item:

- `Audio Books`

Add screens:

1. `AudioBookListPage`
   - title
   - language
   - status
   - pages count
   - creator
   - updated date
   - actions: edit, preview, publish/unpublish, delete

2. `AudioBookCreateEditPage`
   - title
   - description
   - cover image
   - language
   - school/platform scope according to role
   - save as draft

3. `AudioBookPagesEditorPage`
   - list pages
   - add page
   - edit page
   - delete page
   - reorder pages
   - page status
   - approve status

4. `AudioBookPageEditor`
   - page image upload and preview
   - official text editor
   - audio upload and player
   - language selector
   - generate synchronization button
   - local AI model status
   - progress display
   - transcript similarity score
   - synchronized preview
   - manual timestamp editor
   - approve page button

5. `OfflineAIModelSettings`
   - selected model ID
   - install status
   - model version/revision
   - storage estimate
   - persistent storage status
   - install model
   - test model
   - reinstall model
   - delete local model/cache when feasible

Add this user-facing note:

```text
The AI model is saved on this browser/device. It may need to be downloaded again if site data is cleared, browser cache is removed, or the app version changes.
```

## Phase 4 - Browser AI Worker

Use Transformers.js with a browser-compatible multilingual Whisper model.

Recommended MVP model:

- use a tiny/base multilingual Whisper model supported by Transformers.js
- do not use English-only models
- define model ID in one constants file

Create modules:

- `audio/decodeAudioTo16kMono(file: File): Promise<Float32Array>`
- `ai/transcription.worker.ts`
- `ai/transcriptionClient.ts`
- `alignment/normalizeText.ts`
- `alignment/createAlignmentFromTranscript.ts`
- `alignment/validateAlignment.ts`
- `storage/localAudioBookDrafts.ts`

Worker messages:

`load-model`

Input:

```json
{ "type": "load-model" }
```

Output:

```json
{ "type": "model-ready" }
```

Progress:

```json
{ "type": "model-progress", "progress": {} }
```

`transcribe`

Input:

```json
{
  "type": "transcribe",
  "requestId": "string",
  "audio": "Float32Array transferred",
  "language": "en"
}
```

Output:

```json
{
  "type": "transcription-complete",
  "requestId": "string",
  "result": {
    "text": "string",
    "chunks": [
      { "text": "word", "timestamp": [0.32, 0.51] }
    ]
  }
}
```

Error:

```json
{
  "type": "processing-error",
  "requestId": "string",
  "message": "friendly message"
}
```

Use transferable objects when sending audio to the worker.

## Phase 5 - Text Alignment

Implement alignment so official text stays unchanged.

Keep:

- `officialText`: exact teacher text rendered to the reader
- `normalizedTokens`: internal matching tokens with mapping to official tokens

Normalization:

- trim whitespace
- collapse repeated spaces
- lowercase for matching
- normalize apostrophes
- remove/normalize punctuation for matching
- keep original token mapping
- provide wrappers for `normalizeEnglish`, `normalizeFrench`, `normalizeArabic`

Use dynamic programming / Levenshtein-style alignment between official tokens and transcribed tokens.

Statuses:

- `matched`
- `interpolated`
- `unmatched`
- `manually-edited`
- `not-spoken`

Rules:

- matched official word gets transcribed timestamp
- missing official word between matched neighbors gets interpolated timestamp
- missing official word without safe neighbors becomes unmatched
- extra transcribed words are ignored but included in review report
- low similarity or many unmatched/interpolated words sets `review.requiresReview = true`

Function:

```ts
createAlignmentFromTranscript({
  officialText,
  transcribedText,
  transcriptChunks,
  language,
  audioDurationMs
}): PageAlignment
```

Alignment JSON shape:

```json
{
  "version": 1,
  "language": "en",
  "audioDurationMs": 6300,
  "officialText": "The little bird flew over the tall tree.",
  "transcribedText": "The little bird flew over the tree.",
  "similarity": 0.93,
  "model": {
    "provider": "transformers.js",
    "id": "MODEL_ID",
    "version": "MODEL_VERSION_OR_REVISION"
  },
  "words": [
    {
      "index": 0,
      "text": "The",
      "startMs": 320,
      "endMs": 510,
      "status": "matched",
      "confidence": null
    }
  ],
  "review": {
    "requiresReview": true,
    "unmatchedOfficialWords": ["tall"],
    "extraTranscribedWords": [],
    "warnings": []
  }
}
```

## Phase 6 - Preview And Manual Correction

Preview must show:

- audio player
- page image
- official text split into clickable word spans
- active word highlight by `audio.currentTime`
- styling for `matched`, `interpolated`, `unmatched`, `manually-edited`, `not-spoken`
- warnings
- similarity score
- transcribed text comparison
- manual correction controls

Manual correction:

- click a word
- set start time from current audio time
- set end time from current audio time
- manually edit start/end milliseconds
- mark word as not spoken
- mark edited word as `manually-edited`
- approve page

Never overwrite manual edits unless the user explicitly chooses `Regenerate and replace timings`.

## Phase 7 - Local Drafts And PWA

Use IndexedDB for MVP.

Save:

- unsaved audiobook metadata
- page metadata
- official text
- alignment JSON
- processing status
- file blobs if practical

Provide:

- restore draft after refresh
- clear draft after successful upload
- warning if unsaved local drafts exist

If app is not already a PWA, add minimal PWA support:

- manifest
- service worker
- app shell cache
- offline fallback page

Do not cache private uploaded media globally in the service worker. Let Transformers.js/browser cache handle model files.

Use:

- `navigator.storage.estimate()`
- `navigator.storage.persist()`
- `navigator.storage.persisted()`

## Phase 8 - Reader Frontend

If the reader repo is present, implement. If not, create a reader frontend task prompt file.

Reader audiobook page:

- list published audiobooks
- open audiobook detail
- page image
- official text
- audio player
- word highlighting synchronized to audio
- previous/next page
- seeking
- playback speed
- optional auto-next page
- progress save/restore

Implementation:

- use `requestAnimationFrame` while audio plays
- use binary search to find active word:

```ts
currentMs = audio.currentTime * 1000
activeWord = words.find(word => word.startMs <= currentMs && currentMs < word.endMs)
```

- clicking a timestamped word seeks audio to `startMs`
- words without timestamps must not break playback

Readers must not import or bundle Transformers.js/Whisper code.

## Error Handling

Show friendly messages for:

- AI model not installed
- model download failed
- browser does not support required APIs
- WebGPU unavailable, fallback to WASM
- audio decode failed
- audio too long
- out of memory
- transcription failed
- transcript does not match official text
- storage quota too low
- persistent storage denied
- upload failed
- invalid timestamp JSON

Do not show raw stack traces in UI.

## Security And Privacy

- Do not send audio to external AI APIs.
- AI processing stays local in the creator browser.
- Backend receives only uploaded files and final JSON.
- Enforce backend authorization.
- Prevent readers from accessing drafts.
- Validate all uploaded files server-side.
- Validate alignment JSON server-side.
- Do not rely on client-only validation.

## Acceptance Criteria

The feature is complete when:

1. Admin/teacher can create an audiobook.
2. Admin/teacher can add pages with image, text, and audio.
3. Admin/teacher can install/load the local AI model in the browser.
4. Speech-to-text runs client-side in a Web Worker.
5. The browser generates word-level timestamps.
6. Official text remains unchanged.
7. Transcript words are aligned to official text.
8. Unmatched/interpolated words are marked for review.
9. Admin/teacher can preview synchronized playback.
10. Admin/teacher can manually edit timestamps.
11. Admin/teacher can approve pages.
12. Book can be published only when all pages are approved.
13. Reader can open a published audiobook.
14. Reader sees image, text, audio player, and synchronized word highlighting.
15. Reader does not load the AI model.
16. Draft books are not visible to readers.
17. Backend validates permissions and timestamp JSON.
18. PWA/local draft behavior protects creator work after refresh.
19. Local model is reused after first download when browser storage is not cleared.
20. Existing app features continue working.

## Strong Constraints

- Reuse existing conventions.
- Keep code modular.
- Avoid huge components.
- Do not add paid APIs.
- Do not add backend AI processing.
- Do not replace official text with AI text.
- Do not break existing reader/admin/teacher flows.
- Do not bypass multi-school access controls.
- Keep frontend AI code out of the reader bundle.
- Use migrations for DB changes.
- Add focused tests for risky logic.

## Suggested First Implementation Step

Start with Phase 1 backend only:

1. Add models.
2. Add migration.
3. Add upload config.
4. Add validation helpers.
5. Add admin/teacher CRUD routes.
6. Add reader published routes.
7. Add backend tests.
8. Create frontend task prompts if frontend apps are not available in the current workspace.
