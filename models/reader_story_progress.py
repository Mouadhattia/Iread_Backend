## @file
# @class ReaderStoryProgress
from datetime import datetime

from extensions import db
from models.book_story import BookStory
from models.user import User


class ReaderStoryProgress(db.Model):
    __tablename__ = 'reader_story_progress'
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey(BookStory.id), primary_key=True)
    current_page = db.Column(db.Integer, nullable=False, default=1)
    zoom = db.Column(db.Float, nullable=False, default=1)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_read_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship(User, backref=db.backref('story_progress', cascade='all, delete-orphan'))
    story = db.relationship(BookStory, backref=db.backref('reader_progress', cascade='all, delete-orphan'))

    def __repr__(self):
        return '<ReaderStoryProgress user=%s story=%s>' % (self.user_id, self.story_id)
