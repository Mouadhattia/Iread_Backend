# Codex Prompt: Reader Jitsi Video Calls For Sessions

You are working on the IREAD reader React frontend. Implement reader-side Jitsi video calls for online sessions.

Read the backend task/spec first if available:

```text
docs/jitsi-session-video-backend-task.md
```

## Goal

Readers/students should be able to join a Jitsi video call for an online session they are approved to attend.

Readers join as non-moderators.

Video calls are only available for sessions where:

```text
location === "online"
```

## Important Rules

- Do not change backend code.
- Use existing reader app routing, API helpers, auth handling, selected-school handling, and styling.
- All API requests must use `credentials: "include"`.
- Reader must pass the selected school context when available.
- Do not expose JWT token text in the UI.
- Do not show video-call join button for classroom sessions.
- Do not allow pending/unapproved session requests to join.

## Backend API

Reader video-call token route:

```http
GET /reader/sessions/:sessionId/video-call?school_id=1
```

Expected response:

```json
{
  "session_id": 25,
  "room": "iread-session-25-8c3f9a",
  "domain": "meeting.intellect.tn",
  "token": "jwt...",
  "url": "https://meeting.intellect.tn/iread-session-25-8c3f9a?jwt=jwt...",
  "is_moderator": false,
  "location": "online"
}
```

## Where To Add UI

Add join-video-call actions in the reader areas that already show sessions:

- Reader dashboard current/followed sessions.
- Session details page if one exists.
- Any “my sessions” or “current sessions” list.

Only show the join call button when:

- Session `location` is `online`.
- Session follow/request is approved.
- Session has an id.

If the existing data does not include `location`, update the frontend to rely on the route error or request backend to include it in session responses.

## Button Behavior

Button text:

```text
Join Call
```

When clicked:

1. Determine selected school id from URL/query/context/localStorage.
2. Call:

```http
GET /reader/sessions/:sessionId/video-call?school_id=<selectedSchoolId>
```

3. Use `credentials: "include"`.
4. Open `response.url` in a new tab.

Example:

```ts
const response = await fetch(
  `${API_URL}/reader/sessions/${sessionId}/video-call?school_id=${schoolId}`,
  {
    method: "GET",
    credentials: "include"
  }
);
```

Then:

```ts
window.open(data.url, "_blank", "noopener,noreferrer");
```

If popup is blocked, show a fallback button/link.

## Selected School Context

Reader sessions are school-scoped.

When the user is on:

```text
/dashboard?school_id=1
```

the video-call request should include:

```text
?school_id=1
```

If the app stores selected school in context/localStorage, use that same selected school id.

## Meeting Display Options

Preferred first implementation:

- Open Jitsi in a new tab using backend `url`.

Optional future implementation:

- Embed Jitsi using the Jitsi External API.

If embedding later, use:

```ts
domain: response.domain
roomName: response.room
jwt: response.token
```

Do not store the JWT in localStorage.

## Error States

Handle backend errors:

- Session not found.
- Session is not online.
- User is not approved for this session.
- User does not belong to selected school.
- Token generation failed.
- Popup blocked.

Show the backend message clearly.

## UX Requirements

- Keep the action simple and visible for online sessions.
- Use a video icon if the app already uses icons.
- Disable or hide join button for pending session requests.
- If pending sessions are displayed, show status but no active call button.
- On mobile, the button should remain easy to tap.

## Out Of Scope

- Do not implement admin/teacher moderator UI in this task.
- Do not change backend routes.
- Do not configure Jitsi server.
- Do not add recording/transcription controls.
- Do not display JWT token directly.

## Acceptance Criteria

- Approved online sessions show `Join Call`.
- Classroom sessions do not show active join call button.
- Pending/unapproved sessions cannot join.
- Clicking `Join Call` fetches reader video-call data with selected `school_id`.
- Meeting opens with backend `url`.
- JWT is not displayed or stored.
- Errors are shown clearly.
- Existing dashboard/session flows still work.
