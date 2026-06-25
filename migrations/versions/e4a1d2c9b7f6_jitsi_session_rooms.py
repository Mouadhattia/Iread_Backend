"""jitsi session rooms

Revision ID: e4a1d2c9b7f6
Revises: c2b7e9a4d8f1
Create Date: 2026-06-12 00:00:00.000000

"""
import uuid
from urllib.parse import quote

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4a1d2c9b7f6'
down_revision = 'c2b7e9a4d8f1'
branch_labels = None
depends_on = None


JITSI_DOMAIN = 'meeting.intellect.tn'


def build_room(session_id, token):
    suffix = (token or uuid.uuid4().hex)[:8]
    return f'iread-session-{session_id}-{suffix}'


def build_meet_link(room):
    return f'https://{JITSI_DOMAIN}/{quote(room)}'


def upgrade():
    op.add_column('session', sa.Column('jitsi_room', sa.String(length=255), nullable=True))
    op.create_index('ix_session_jitsi_room', 'session', ['jitsi_room'], unique=True)

    connection = op.get_bind()
    online_sessions = connection.execute(sa.text(
        """
        SELECT id, token
        FROM session
        WHERE location = 'ONLINE' OR location = 'online'
        """
    )).fetchall()
    for session_id, token in online_sessions:
        room = build_room(session_id, token)
        connection.execute(
            sa.text(
                """
                UPDATE session
                SET jitsi_room = :room,
                    meet_link = :meet_link
                WHERE id = :session_id
                """
            ),
            {
                'room': room,
                'meet_link': build_meet_link(room),
                'session_id': session_id
            }
        )


def downgrade():
    op.drop_index('ix_session_jitsi_room', table_name='session')
    op.drop_column('session', 'jitsi_room')
