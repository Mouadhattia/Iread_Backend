## @file
# @class WordSense
from datetime import datetime

from extensions import db


##
# @brief Table for storing a single word-sense's lexical facts: lemma, POS,
# dictionary enrichment, and CEFR level (which may be absent/unresolved).
#
class WordSense(db.Model):
    __tablename__ = 'word_sense'

    id = db.Column(db.Integer, primary_key=True)
    lemma = db.Column(db.String(100), nullable=False, index=True)
    pos = db.Column(db.String(16), nullable=False, index=True)
    # '' means the sense hasn't been disambiguated beyond lemma+POS (see T8).
    sense_key = db.Column(db.String(64), nullable=False, default='')

    definition = db.Column(db.Text, nullable=True)
    synonyms = db.Column(db.JSON, nullable=True)
    example_sentence = db.Column(db.Text, nullable=True)

    cefr_level = db.Column(db.String(2), nullable=True, index=True)
    cefr_source = db.Column(db.String(64), nullable=True)

    cefr_override_level = db.Column(db.String(2), nullable=True)
    cefr_override_note = db.Column(db.String(255), nullable=True)
    cefr_override_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    cefr_override_at = db.Column(db.DateTime, nullable=True)

    # Permanent editor-confirmed exclusion (e.g. proper nouns) — never counts
    # as unresolved once set, never gets defaulted into a CEFR band.
    proper_noun_excluded = db.Column(db.Boolean, nullable=False, default=False)

    # Provenance for direct dictionary edits (school/CEFR-suggestion workflow
    # governs who's allowed to write these fields directly vs. only suggest).
    enrichment_updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    enrichment_updated_at = db.Column(db.DateTime, nullable=True)

    frequency_rank = db.Column(db.Integer, nullable=True)
    theme_tags = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    overridden_by = db.relationship('User', foreign_keys=[cefr_override_by])
    enrichment_updater = db.relationship('User', foreign_keys=[enrichment_updated_by])

    __table_args__ = (
        db.UniqueConstraint('lemma', 'pos', 'sense_key', name='uq_word_sense_lemma_pos_sense'),
    )

    @property
    def effective_cefr_level(self):
        return self.cefr_override_level or self.cefr_level

    @property
    def is_unresolved(self):
        return not self.proper_noun_excluded and self.effective_cefr_level is None

    def __repr__(self):
        return '<WordSense %s/%s/%s>' % (self.lemma, self.pos, self.sense_key or '-')
