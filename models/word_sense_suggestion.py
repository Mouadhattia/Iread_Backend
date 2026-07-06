## @file
# @class WordSenseSuggestion
from datetime import datetime

from extensions import db
from models.shcool import Shcool
from models.word_sense import WordSense

SUGGESTION_TYPE_CEFR = 'cefr'
SUGGESTION_TYPE_DICTIONARY = 'dictionary'
SUGGESTION_TYPES = (SUGGESTION_TYPE_CEFR, SUGGESTION_TYPE_DICTIONARY)

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'
STATUS_SUPERSEDED = 'superseded'


##
# @brief A school's proposed change to a word-sense (CEFR level/proper-noun
# exclusion, or dictionary enrichment) — never applied to the live WordSense
# row until a super admin approves it. Multiple schools can each have their
# own pending suggestion for the same word; approving one supersedes the rest.
class WordSenseSuggestion(db.Model):
    __tablename__ = 'word_sense_suggestion'

    id = db.Column(db.Integer, primary_key=True)
    word_sense_id = db.Column(db.Integer, db.ForeignKey(WordSense.id), nullable=False, index=True)
    school_id = db.Column(db.Integer, db.ForeignKey(Shcool.id), nullable=False, index=True)
    suggestion_type = db.Column(db.String(16), nullable=False)

    suggested_cefr_level = db.Column(db.String(2), nullable=True)
    suggested_proper_noun_excluded = db.Column(db.Boolean, nullable=True)
    suggested_definition = db.Column(db.Text, nullable=True)
    suggested_synonyms = db.Column(db.JSON, nullable=True)
    suggested_example_sentence = db.Column(db.Text, nullable=True)

    note = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(16), nullable=False, default=STATUS_PENDING, index=True)

    suggested_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    suggested_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.String(500), nullable=True)

    word_sense = db.relationship(WordSense, backref=db.backref('suggestions', cascade='all, delete-orphan'))
    school = db.relationship(Shcool)
    suggester = db.relationship('User', foreign_keys=[suggested_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return '<WordSenseSuggestion word_sense=%s school=%s type=%s status=%s>' % (
            self.word_sense_id, self.school_id, self.suggestion_type, self.status,
        )
