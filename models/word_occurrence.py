## @file
# @class WordOccurrence
from datetime import datetime

from extensions import db
from models.chapter import Chapter
from models.word_sense import WordSense


##
# @brief Many-to-many link recording that a word-sense occurs in a chapter,
# keeping the printed surface form and the example line for that occurrence.
#
class WordOccurrence(db.Model):
    __tablename__ = 'word_occurrence'

    id = db.Column(db.Integer, primary_key=True)
    word_sense_id = db.Column(db.Integer, db.ForeignKey(WordSense.id), nullable=False, index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey(Chapter.id), nullable=False, index=True)
    surface_form = db.Column(db.String(100), nullable=False)
    example_line = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    word_sense = db.relationship(WordSense, backref=db.backref('occurrences', cascade='all, delete-orphan'))
    chapter = db.relationship(Chapter, backref=db.backref('word_occurrences', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('word_sense_id', 'chapter_id', name='uq_word_occurrence_sense_chapter'),
    )

    def __repr__(self):
        return '<WordOccurrence sense=%s chapter=%s>' % (self.word_sense_id, self.chapter_id)
