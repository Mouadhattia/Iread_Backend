## @file 
#@class Session
from extensions import db
from models.book import Book
from models.user import Teacher
from enum import Enum
from models.pack import Pack
from models.unit import Unit

class Location(Enum):
    ONLINE='online'
    CLASSROOM='classroom'

##
# @brief Table for storing information about sessions.
#
class Session(db.Model):
    __tablename__="session"
    id=db.Column(db.Integer,primary_key=True)
    token=db.Column(db.String(36),unique=True)
    name=db.Column(db.String(65),nullable=False)
    img=db.Column(db.String(100),nullable=True)
    capacity=db.Column(db.Integer,default=20)
    book_id=db.Column(db.ForeignKey(Book.id))
    unit_id=db.Column(db.ForeignKey(Unit.id),nullable=True)
    teacher_id=db.Column(db.ForeignKey(Teacher.id))
    price=db.Column(db.Float,default=0)
    discount=db.Column(db.Float,default=0)
    location=db.Column(db.Enum(Location),default=Location.ONLINE)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    pack_id=db.Column(db.ForeignKey(Pack.id))
    description = db.Column(db.String(200))
    active=db.Column(db.Boolean,nullable=False,default=False)
    meet_link = db.Column(db.String(100),nullable=True)     
    
  

    def __repr__(self):
        return '< Session %s >' %self.date