from datetime import datetime
from extensions import db
from models.session import Session
from models.user import User


class Chat(db.Model):
    __tablename__ = 'chat'

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.ForeignKey(User.id))
    session_id = db.Column(db.ForeignKey(Session.id))

   