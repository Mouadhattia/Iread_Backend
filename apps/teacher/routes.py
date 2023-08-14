from flask import Blueprint,abort,jsonify,request
from flask_login import login_required,current_user

from models.user import Teacher

from functools import wraps
from apps.reader.routes import bcrypt
from extensions import db

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.type not in ['teacher','admin']:
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function


teacher = Blueprint('teacher', __name__, url_prefix='/teacher')

@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    Teacher.query.filter_by(email=current_user.email).first()

    return jsonify({
        'username':current_user.username,
        'email':current_user.email,
        'description':current_user.description,
        'study_level':current_user.study_level
        }),200