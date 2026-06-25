# Backend Task: Jitsi Video Calls For Online Sessions

Do not implement frontend in this task.

## Goal

Add Jitsi video-call support for IREAD sessions.

When a session is `online`, the backend should be able to create/provide a Jitsi meeting room and generate a signed JWT token for users who are allowed to join the session.

School admins and teachers should join as moderators. Readers/students should join as non-moderators.

## Jitsi Server Info

Jitsi domain:

```text
meeting.intellect.tn
```

JWT config:

```text
aud: jitsi
iss: intellect
sub: meeting.intellect.tn
algorithm: HS256
secret: process.env.CALL_JWT_SECRET || "intellect"
```

Use environment variables in Flask:

```text
CALL_JWT_SECRET=intellect
JITSI_APP_ID=intellect
JITSI_DOMAIN=meeting.intellect.tn
JITSI_AUD=jitsi
JITSI_TOKEN_TTL_SECONDS=36000
```

## Existing Session Context

The backend already has `Session.location` with:

```text
online
classroom
```

Only sessions with `location == online` should expose video-call data.

The `Session` model already has:

```text
meet_link
```

Recommended:

- Reuse `Session.meet_link` for the Jitsi room URL.
- Add a new nullable column if needed:

```text
jitsi_room
```

If adding `jitsi_room`, create a migration.

## Room Naming

Generate a stable room name per session.

Recommended format:

```text
iread-session-<session_id>-<session_token_or_uuid>
```

Do not use raw session names only, because two sessions can have the same name.

Example:

```text
iread-session-25-8c3f9a
```

Meeting URL:

```text
https://meeting.intellect.tn/<room>?jwt=<token>
```

Return the token separately too, so frontends can use the Jitsi iframe API.

## JWT Payload

Generate the same style of token as this JavaScript example:

```js
const generate = ({ name, isModerator, room, email }) => {
  const now = Math.floor(Date.now() / 1000);
  const secretJwt = process.env.CALL_JWT_SECRET || "intellect";

  const payload = {
    aud: "jitsi",
    iss: "intellect",
    sub: "meeting.intellect.tn",
    room: room,
    nbf: now - 10,
    exp: now + 10 * 60 * 60,
    context: {
      user: {
        id: uuid(),
        name: name,
        email: email,
        moderator: !!isModerator
      },
      features: {
        livestreaming: true,
        transcription: false,
        recording: true
      }
    }
  };

  return jsonwebtoken.sign(payload, secretJwt, { algorithm: "HS256" });
};
```

Python implementation should use `PyJWT`.

If `PyJWT` is not installed, add it to `requirements.txt`:

```text
PyJWT
```

## Backend Helper

Create a helper similar to:

```python
def generate_jitsi_token(user, room, is_moderator):
    now = int(time.time())
    payload = {
        "aud": ConfigClass.JITSI_AUD,
        "iss": ConfigClass.JITSI_APP_ID,
        "sub": ConfigClass.JITSI_DOMAIN,
        "room": room,
        "nbf": now - 10,
        "exp": now + ConfigClass.JITSI_TOKEN_TTL_SECONDS,
        "context": {
            "user": {
                "id": str(uuid.uuid4()),
                "name": user.username,
                "email": user.email,
                "moderator": bool(is_moderator)
            },
            "features": {
                "livestreaming": True,
                "transcription": False,
                "recording": True
            }
        }
    }
    return jwt.encode(payload, ConfigClass.CALL_JWT_SECRET, algorithm="HS256")
```

## Access Rules

### Moderator

User should be moderator when:

- `current_user.type == "super_admin"`
- `current_user.type == "admin"` and the session belongs to their school or an accessible global pack/session
- `current_user.type == "teacher"` and they are the assigned session teacher
- optional: global teacher can moderate global sessions if your current backend supports global teachers

### Reader

Reader can join only when:

- Session is online.
- Reader belongs to the selected school context.
- Reader has approved `Follow_session` for this session.

Recommended:

```text
Follow_session.approved == True
```

If the product wants pending readers to see a disabled state, return 403 with a clear message.

### Time Window

Optional but recommended:

- Allow joining 15 minutes before `Session.start_date`.
- Allow joining until `Session.end_date`.

If not implementing time-window restriction yet, leave a clear TODO.

## Proposed Routes

### Admin/Teacher Moderator Token

```http
GET /admin/sessions/:sessionId/video-call
```

Returns moderator token for school admin/super admin when authorized.

Response:

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

If teachers use a separate teacher app/API, also add:

```http
GET /teacher/sessions/:sessionId/video-call
```

### Reader Token

```http
GET /reader/sessions/:sessionId/video-call?school_id=1
```

Returns non-moderator token for approved readers.

Response:

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

## Session Create/Update Behavior

When school admin creates or updates a session:

- If `location` is `online`, ensure a Jitsi room exists.
- If `location` is `classroom`, do not generate a Jitsi room.
- Preserve existing `meet_link` behavior if the frontend already uses it.

If using `Session.meet_link`, set:

```text
https://meeting.intellect.tn/<room>
```

Do not store JWT in the database. Generate JWT per request.

## Security Notes

- Never return moderator token to readers.
- Never generate video token for classroom sessions.
- Never store JWT tokens permanently.
- Use environment variables for secrets.
- Keep token TTL limited.
- Use session/user access checks before generating tokens.

## Migration Notes

If adding `jitsi_room`, migration should:

- Add nullable `session.jitsi_room`.
- Backfill online sessions with stable room names.
- Optionally set `meet_link` for online sessions.

If only reusing `meet_link`, no DB migration may be needed.

## Acceptance Criteria

- Online sessions can provide Jitsi video-call data.
- Classroom sessions return 400 or 404 for video-call requests.
- Admin/super admin/assigned teacher gets moderator token.
- Approved reader gets non-moderator token.
- Unapproved reader cannot join.
- JWT payload matches Jitsi config.
- Existing session create/update/list routes still work.
- No JWT is stored in the database.
