# Codex Prompt: Admin Dashboard Jitsi Video Calls

You are working on the IREAD React admin dashboard. Implement the admin/teacher side of Jitsi video calls for online sessions.

Read the backend task/spec first if available:

```text
docs/jitsi-session-video-backend-task.md
```

## Goal

School admins, super admins, and authorized teachers should be able to open a Jitsi video call for an online session from the dashboard.

Video calls are only available for sessions where:

```text
location === "online"
```

Classroom sessions should not show a join video-call action.

## Important Rules

- Do not change backend code.
- Use existing dashboard routing, API helpers, auth handling, and styling.
- All API requests must use `credentials: "include"`.
- Same dashboard is used by school admin and super admin.
- Do not expose reader/student video tokens in admin UI.
- Do not show video-call controls for classroom sessions.

## Backend API

Moderator token route:

```http
GET /admin/sessions/:sessionId/video-call
```

Expected response:

```json
{
  "session_id": 25,
  "room": "iread-session-25-8c3f9a",
  "domain": "meeting.intellect.tn",
  "token": "jwt...",
  "url": "https://meeting.intellect.tn/iread-session-25-8c3f9a?jwt=jwt...",
  "is_moderator": true,
  "location": "online"
}
```

If the teacher app uses teacher routes, teacher dashboard can use:

```http
GET /teacher/sessions/:sessionId/video-call
```

Only use that if the teacher frontend exists separately.

## UI Tasks

### Session List

On session list/table/cards:

- If session is online, show a video-call action.
- Use a clear video icon/button, for example `Video`.
- If session is classroom, hide the video-call action or show it disabled with tooltip.

Button behavior:

```text
Open Call
```

When clicked:

1. Call `GET /admin/sessions/:sessionId/video-call`.
2. Receive `url`, `domain`, `room`, and `token`.
3. Open the call.

### Session Details

On session details page:

- Show video-call panel only for online sessions.
- Include:
  - Room name
  - Join as moderator button
  - Copy meeting link button if backend returns `url`

Do not show JWT token directly in UI.

### Create/Edit Session Form

When creating or editing a session:

- If `location` is `online`, show a note or field area that the video room will be created automatically by backend.
- If `location` is `classroom`, hide video-call options.
- Do not ask admins to manually paste JWT tokens.

If the backend returns `meet_link` or room data in session details, display it read-only.

## Opening The Call

Preferred option:

- Open `response.url` in a new browser tab.

```ts
window.open(response.url, "_blank", "noopener,noreferrer");
```

Alternative option if the dashboard already embeds meeting iframes:

- Use Jitsi External API with:

```ts
domain: response.domain
roomName: response.room
jwt: response.token
```

Do not implement iframe embedding unless the dashboard already has a safe pattern for it.

## API Helper Example

Use existing API client if available. Otherwise:

```ts
const response = await fetch(`${API_URL}/admin/sessions/${sessionId}/video-call`, {
  method: "GET",
  credentials: "include"
});
```

Handle non-200 responses and display backend message.

## Error States

Handle:

- Session is not online.
- User is not authorized.
- Session not found.
- Backend token generation failed.
- Popup blocked when opening new tab.

If popup is blocked, show a visible fallback link/button using `response.url`.

## Role Behavior

Super admin:

- Can open calls for global/platform sessions if backend allows.

School admin:

- Can open calls only for sessions accessible to their school.
- Should receive moderator token.

Teacher:

- Can open call only if assigned to the session or backend allows global-teacher moderation.
- Should receive moderator token.

## Out Of Scope

- Do not implement reader/student meeting UI in this task.
- Do not change backend routes.
- Do not implement Jitsi server configuration.
- Do not store JWT in localStorage/sessionStorage.

## Acceptance Criteria

- Online sessions show an `Open Call` action.
- Classroom sessions do not show active video-call action.
- Clicking `Open Call` fetches moderator call data.
- Meeting opens using backend `url`.
- JWT token is never shown directly.
- Unauthorized/backend errors are displayed clearly.
- Existing session create/edit/list flows still work.
