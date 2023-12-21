from extensions import db
from models.user import User
from datetime import datetime

class UserLog(db.Model):
    __tablename__ = "user_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_agent = db.Column(db.String(200))
    user_ip = db.Column(db.String(15))
    referer = db.Column(db.String(200))
    user_country = db.Column(db.String(100), nullable=True)
    user_city = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.ForeignKey(User.id), nullable=True)
    visit_duration = db.Column(db.Float ,default=0)
    browser = db.Column(db.String(200),nullable=True)
    system = db.Column(db.String(200),nullable=True)
    user_cookie_id = db.Column(db.String(255))
    created_at=db.Column(db.Date,nullable=False,default=datetime.now())


    def __init__(self, user_agent, user_ip, referer, user_country, user_city, user_cookie_id ,browser,system,user_id=None):
        self.user_agent = user_agent
        self.user_ip = user_ip
        self.referer = referer
        self.user_country = user_country
        self.user_city = user_city
        self.user_id = user_id
        self.user_cookie_id = user_cookie_id 
        self.system = system
        self.browser = browser
    def __repr__(self):
        return f'<UserLog user_ip={self.user_ip}>'
