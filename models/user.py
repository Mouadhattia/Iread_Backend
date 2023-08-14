## @file
# @class User
# @class Reader
# @class Teacher
# @class Admin

from datetime import datetime
from flask_login import UserMixin
from extensions import db

##
# @brief Base class for users with common attributes and behaviors.
#
class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hashed = db.Column(db.String(100), unique=True, nullable=False)
    img = db.Column(db.String(300),default="https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/User-avatar.svg/2048px-User-avatar.svg.png")
    confirmed = db.Column(db.Boolean, default=False)
    approved = db.Column(db.Boolean, default=False)
    created_at=db.Column(db.Date,nullable=False,default=datetime.now())
    type = db.Column(db.String(20))

    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'user'
    }

    def __repr__(self):
        return '<User %s>' % self.username


##
# @brief Class representing a reader user.
#
class Reader(User):
    __tablename__ = "reader"
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    level=db.Column(db.String(10),nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'reader'}
    
    def __repr__(self):
        return '<Reader %s>' % self.username


##
# @brief Class representing a teacher user.
#
class Teacher(User):
    __tablename__ = "teacher"
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    description=db.Column(db.String(400),nullable=False)
    study_level=db.Column(db.String(40),nullable=False)
    available=db.Column(db.Boolean,nullable=False,default=True)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}
    
    def __repr__(self):
        return '<Teacher %s>' % self.username


##
# @brief Class representing a admin user.
#
class Admin(User):
    __tablename__ = "admin"
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    __mapper_args__ = {'polymorphic_identity': 'admin'}
    
    def __repr__(self):
        return '<Admin %s>' % self.username
