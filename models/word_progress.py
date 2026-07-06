## @file
# @brief Per-learner word mastery, evidence, streak, and achievement records
# (the Achievement & Word-Progress System brief). Attempts from both daily-run
# and practice modes write here identically — mode never affects stage, pips,
# or mastery, only a separate daily-run ranking that lives outside this module.
from datetime import datetime

from extensions import db
from models.user import User
from models.word_sense import WordSense

STAGE_ENCOUNTERED = 'encountered'
STAGE_GUESSED = 'guessed'
STAGE_KNOWN = 'known'
STAGE_MASTERED = 'mastered'

# Matches apps/game_calendar.py's GAME_* constants (lowercase, hyphenated).
GAME_KEYS = ('bee-genius', 'word-explorer', 'think-word', 'intellect-link')


class WordProgress(db.Model):
    __tablename__ = 'word_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    word_sense_id = db.Column(db.Integer, db.ForeignKey(WordSense.id), nullable=False, index=True)

    stage = db.Column(db.String(16), nullable=False, default=STAGE_ENCOUNTERED)

    # One pip per game, set only by a clear with zero hints (section 5).
    pip_bee_genius = db.Column(db.Boolean, nullable=False, default=False)
    pip_word_explorer = db.Column(db.Boolean, nullable=False, default=False)
    pip_think_word = db.Column(db.Boolean, nullable=False, default=False)
    pip_intellect_link = db.Column(db.Boolean, nullable=False, default=False)

    # Cached from WordProgressEvidence — recomputed on every correct attempt.
    distinct_sources_count = db.Column(db.Integer, nullable=False, default=0)
    distinct_days_count = db.Column(db.Integer, nullable=False, default=0)
    has_unaided_clear = db.Column(db.Boolean, nullable=False, default=False)
    consecutive_no_hint_clears = db.Column(db.Integer, nullable=False, default=0)

    first_encountered_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    first_guessed_at = db.Column(db.DateTime, nullable=True)
    first_known_at = db.Column(db.DateTime, nullable=True)
    mastered_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    user = db.relationship(User, backref=db.backref('word_progress', cascade='all, delete-orphan'))
    word_sense = db.relationship(WordSense, backref=db.backref('learner_progress', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'word_sense_id', name='uq_word_progress_user_word_sense'),
    )

    @property
    def pip_count(self):
        return sum([
            self.pip_bee_genius, self.pip_word_explorer,
            self.pip_think_word, self.pip_intellect_link,
        ])

    def __repr__(self):
        return '<WordProgress user=%s word_sense=%s stage=%s>' % (self.user_id, self.word_sense_id, self.stage)


class WordProgressEvidence(db.Model):
    """One row per correct clear — the append-only log the mastery rule (2+
    sources, 2+ days, 1+ unaided) is computed from."""
    __tablename__ = 'word_progress_evidence'

    id = db.Column(db.Integer, primary_key=True)
    word_progress_id = db.Column(db.Integer, db.ForeignKey(WordProgress.id), nullable=False, index=True)
    source = db.Column(db.String(32), nullable=False)  # one of GAME_KEYS, or 'typed_from_memory'
    mode = db.Column(db.String(16), nullable=False)  # 'daily' or 'practice' — never affects mastery
    occurred_on = db.Column(db.Date, nullable=False, index=True)
    hints_used = db.Column(db.Integer, nullable=False, default=0)
    heaviest_hint_tier = db.Column(db.String(16), nullable=True)  # 'light'|'medium'|'heavy'|None
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    word_progress = db.relationship(
        WordProgress,
        backref=db.backref('evidence', cascade='all, delete-orphan', order_by='WordProgressEvidence.created_at'),
    )

    def __repr__(self):
        return '<WordProgressEvidence source=%s day=%s hints=%s>' % (self.source, self.occurred_on, self.hints_used)


class UserStreak(db.Model):
    """One shared 'played today' streak covering both modes (section 11)."""
    __tablename__ = 'user_streak'

    user_id = db.Column(db.Integer, db.ForeignKey(User.id), primary_key=True)
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    best_streak = db.Column(db.Integer, nullable=False, default=0)
    last_played_on = db.Column(db.Date, nullable=True)
    grace_available = db.Column(db.Boolean, nullable=False, default=True)
    grace_used_on = db.Column(db.Date, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    user = db.relationship(User, backref=db.backref('streak', uselist=False, cascade='all, delete-orphan'))

    def __repr__(self):
        return '<UserStreak user=%s current=%s best=%s>' % (self.user_id, self.current_streak, self.best_streak)


class UserAchievement(db.Model):
    __tablename__ = 'user_achievement'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    achievement_key = db.Column(db.String(64), nullable=False)
    tier = db.Column(db.Integer, nullable=True)
    earned_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    context = db.Column(db.JSON, nullable=True)

    user = db.relationship(User, backref=db.backref('achievements', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_key', 'tier', name='uq_user_achievement_key_tier'),
    )

    def __repr__(self):
        return '<UserAchievement user=%s key=%s tier=%s>' % (self.user_id, self.achievement_key, self.tier)


class SelfReportedWord(db.Model):
    """The 'words I already know' shelf (section 8) — typed-from-memory words
    that aren't part of any tracked book. Deliberately kept out of book/CEFR/
    mastery statistics."""
    __tablename__ = 'self_reported_word'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    surface_form = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship(User, backref=db.backref('self_reported_words', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'surface_form', name='uq_self_reported_word_user_surface'),
    )

    def __repr__(self):
        return '<SelfReportedWord user=%s word=%s>' % (self.user_id, self.surface_form)
