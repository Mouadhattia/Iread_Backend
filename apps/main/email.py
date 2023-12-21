## @file

from itsdangerous import URLSafeTimedSerializer
from models.user import User,Reader,Admin,Teacher
from extensions import db 
from datetime import datetime

s=URLSafeTimedSerializer('SECRET_KEY')


## @brief Function that generates a token specific to a new user for account confirmation or email resend.
#
# This function generates a token specific to a new user for confirming their account or resending the confirmation email.
#
# @param email: The email of the user for whom the token is generated.
# @return: The generated token.
# @details: Here's an example of how to use this function:
# >> generate_confirmed_token('nom@gmail.com')
def generate_confirmed_token(email):
    token=s.dumps({'confirm':email})
    return token


##
## @brief Function that checks if the token is valid and up-to-date and updates the 'confirmed' attribute of the user to 1 (True) in this case.
#
# This function verifies if the token is valid and not expired, and then updates the 'confirmed' attribute of the associated user to 1 (True).
# The function uses the 'itsdangerous' library to load and validate the token.
#
# @param token: The token to be verified.
# @return: True if the token is valid and the user's 'confirmed' attribute was updated successfully, otherwise False.
def reader_confirm_token(token):
    try:
        data=s.loads(token.encode('utf-8'),max_age=1200)
    except Exception:
        return False
    reader=Reader.query.filter_by(email=data.get('confirm')).first()
    if reader:
        reader.confirmed = True
        reader.approved = True
        db.session.commit()
        return data.get('confirm')
    else:
        return False

def admin_confirm_token(token):
    try:
        data=s.loads(token.encode('utf-8'),max_age=1200)
    except Exception:
        return False
    user=User.query.filter_by(email=data.get('confirm')).first()
    if user and user.type!='admin':
        reader=Reader.query.filter_by(email=data.get('confirm')).first()
        if reader:
            db.session.delete(reader)
            db.session.commit()
        teacher=Teacher.query.filter_by(email=data.get('confirm')).first()
        if teacher:
            db.session.delete(teacher)
            db.session.commit()

        admin=Admin(username=user.username,email=user.email,password_hashed=user.password_hashed,img=user.img,confirmed=True,created_at=datetime.now())
        print(admin)
        db.session.add(admin)
        db.session.commit()
        return True
    else:
        return False