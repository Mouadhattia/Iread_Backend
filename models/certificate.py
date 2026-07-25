## @file
# @class Certificate
from datetime import datetime

from extensions import db
from models.book import Book
from models.user import User


##
# @brief A durable, portable credential in a reader's Global Reading Passport
# (PRD §2). Issued automatically when a reader reaches a milestone — clearing a
# CEFR band, or mastering every tracked word in a book. A certificate never
# references a school: like the rest of the passport it belongs to the learner
# and survives school changes and closures.
#
class Certificate(db.Model):
    __tablename__ = 'certificate'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False, index=True)
    # 'cefr_band' | 'book_mastery'
    kind = db.Column(db.String(32), nullable=False, index=True)
    # The milestone key this certificate corresponds to (e.g. 'band_cleared_a2',
    # 'book_conqueror_27'); unique per user so issuance is idempotent.
    milestone_key = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    # CEFR level for cefr_band certificates, else NULL.
    cefr_level = db.Column(db.String(10), nullable=True)
    # Book for book_mastery certificates, else NULL.
    book_id = db.Column(db.Integer, db.ForeignKey(Book.id), nullable=True)
    # Stable, human-readable serial shown on the printed certificate.
    serial = db.Column(db.String(40), nullable=False, unique=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship(User, backref=db.backref('certificates', cascade='all, delete-orphan'))
    book = db.relationship(Book)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'milestone_key', name='uq_certificate_user_milestone'),
    )

    def __repr__(self):
        return '<Certificate %s user=%s>' % (self.kind, self.user_id)
