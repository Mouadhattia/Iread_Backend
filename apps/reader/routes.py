## @file
# Blueprint for user readers' authentication.
# Contains routes and functions related to user authentication.
from datetime import datetime
from flask import Blueprint,request,jsonify,render_template, redirect
from flask_bcrypt import Bcrypt
from models.user import User,Reader,Teacher
from models.teacher_postulate import Teacher_postulate
from models.pack import Pack
from models.follow_pack import Follow_pack
from models.book import Book
from models.session import Session
from models.follow_session import Follow_session
from apps.main.email import generate_confirmed_token,reader_confirm_token
from extensions import mail,login_manager,db
from flask_mail import Message
from config import ConfigClass
from flask_login import login_user,logout_user,current_user,login_required
from functools import wraps


## @brief Blueprint for user readers' authentication.
# This blueprint contains routes and functions related to user authentication, including login, registration,
# password hashing, and email verification.
reader = Blueprint('reader', __name__, url_prefix='/reader')


## @brief Create an instance of the Bcrypt class from flask_bcrypt for password hashing.
bcrypt=Bcrypt()

# Initialize the login manager for the authentication blueprint.
login_manager.init_app(reader)


## @brief Load a user from the SQL database based on their unique user_id.
#
# This function is used by the login manager to load a user from the SQL database based on their unique user_id.
# The function accepts a user_id as a parameter and retrieves the corresponding user from the database using the User.query.get() method.
#
# @param user_id: The unique identifier of the user.
# @return: The user object corresponding to the provided user_id, or None if the user with the specified ID is not found.
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


## @brief Check if the email entered by the user already exists in the database.
#
# This function verifies if the email entered by the user already exists in the database.
# The function accepts an email as a parameter and checks if there is a user with the same email using the User.query.filter_by() method.
#
# @param email: The email entered by the user.
# @return: True if the email exists in the database, and False otherwise.
def user_email_exist(email):
    user=User.query.filter_by(email=email).first()
    if user :
        return True
    else:
        return False

## @brief Route for registering new users.
#
# This route is used for registering new users in the system. The function accepts a POST request with JSON data containing the user's username, email, and password.
# The password is encrypted using the Bcrypt object before being stored in the database.
# The new user is then added to the database.
# A confirmation token is generated for the user, encapsulating their email, and an email with a confirmation link is sent to the user.
# If the registration process is successful, a JSON object with information about the registration status and the user's details is returned.
#
# @param username: The username of the new user.
# @param email: The email of the new user.
# @param password: The password of the new user.
#
# @return: A JSON object containing information about the registration status and the user's details.
@reader.route('/register',methods=['POST'])
def register():
    try:
        username=request.json['username']
        email=request.json['email']
        password=request.json['password']
        if user_email_exist(email):
            return jsonify({'message':'This email is already used . Please choose another'}),409 # Conflit
        else:
            password_hash=bcrypt.generate_password_hash(password)
            new_user=Reader(username=username,email=email,password_hashed=password_hash,created_at=datetime.now())
            db.session.add(new_user)
            db.session.commit()
            confirmation_token=generate_confirmed_token(email)
            confirm_link = f"http://localhost:3001/reader/confirm/{confirmation_token}"
            #confirmation_email = render_template('confirm.html',username=username,confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
            msg.body=confirm_link
            #msg.html = confirmation_email
            mail.send(msg)
            return jsonify({'message':'Your account has been sucessfully create.Please verify your emailbox to confirm your account','user':{'username':username,'email':email}}),201
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for confirming the account based on the received email.
#
# This route is used to confirm the user's account based on the token contained in the confirmation email sent to the user.
# The function uses the 'confirm_token' function imported from './email.py' to verify if the link is valid.
# If the link is valid, the 'confirmed' attribute of the user is set to 1 (True).
# A JSON object is returned to notify whether the confirmation process was successful or not.
#
# @param token: Token contained in the confirmation email sent to the user.
#
# @return: A JSON object to notify if the confirmation process was successful or not.
@reader.route('/confirm/<token>')
def confirmation_of_token(token):
    try:
        if reader_confirm_token(token):
            return jsonify({'message':'Your are confirmed sucessfully your account'}),200
        else:
            return jsonify({'message':'Invalid or expired link'}),404
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for resending the confirmation email in case the account confirmation link has expired or is invalid.
#
# This route is used to resend the confirmation email to the user if the account confirmation link has expired or is invalid.
# The function accepts a POST request with JSON data containing the user's email for resending the confirmation link.
# If the provided email exists in the database, a new confirmation token is generated for the user.
# A confirmation link is created using the new token and sent to the user's email.
# If the email exists and the confirmation link is sent successfully, a JSON object with a success message is returned.
# If the email does not exist or the user is not yet registered, a JSON object with an error message is returned.
#
# @param email: The email for resending the confirmation link.
#
# @return: A JSON object containing information about the result of the email resend process.
@reader.route('/resend_email_confirmation_link',methods=['POST'])
def resend_email_confirmation_link():
    try:
        email=request.json['email']
        if user_email_exist(email):
            user=User.query.filter_by(email=email).first()
            username=user.username
            confirmation_token=generate_confirmed_token(email)
            confirm_link = f"http://localhost:5000/reader/confirm/{confirmation_token}"
            #confirmation_email = render_template('confirm.html',username=username,confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
            msg.body=confirm_link
            #msg.html = confirmation_email
            mail.send(msg)
        else:
            return jsonify({'message':'Invalid email or you are not already regiter?'}),404

        return jsonify({'message':'A new email has been sent !!!'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for user readers' login.
#
# This route is used for user readers' login. The function accepts a POST request with JSON data containing the user's email and password.
# The function verifies if the provided email and password match the information in the database.
# If the email and password are correct, and the user's account is confirmed, the user is logged in successfully.
# A JSON object is returned to notify whether the login process was successful or not, along with the user's 'is_admin' status.
#
# @param email: The email entered by the user for login.
# @param password: The password entered by the user for login.
#
# @return: A JSON object to notify if the login process was successful or not, along with the user's 'is_admin' status.
@reader.route('/login',methods=['POST'])
def login():
    try:
        email=request.json['email']
        password=request.json['password']
        user=User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password_hashed,password):
            if user.confirmed:
                if user.approved:
                    login_user(user)
                    return jsonify({'message':'Your are logged in succesfully','role':user.type}),200
                else:
                    return jsonify({'message':'Your are not been approved for the moment'}),403
            else:
                return jsonify({'message':'You don\'t confirm your account'}),403 # Acces interdit
        else:  
            return jsonify({'message':'Invalid email or password'}),404
    
    except Exception as error:
        return jsonify({'message':'Internal server error','error':str(error)}),500


@reader.route('/user_authenticated')
def user_authenticate():
    try:
        print(current_user.is_authenticated)
        if current_user.is_authenticated:
            return jsonify({'is_authenticated':current_user.is_authenticated,'username':current_user.username,'email':current_user.email,'img':current_user.img})
        else:
            return jsonify({'is_authenticated':current_user.is_authenticated})
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route to the reader's dashboard for viewing their profile.
#
# This route is used to display the reader's dashboard and their profile information.
# The route accepts a GET request and requires the user to be logged in.
# The user's dashboard contains details such as their username and email.
# It also fetches information about the formations that the user is following, including those that have already taken place (formation_follow),
# and those that are scheduled for the future (comming_formation).
# The information is then formatted into a JSON object and returned as a response.
#
# @return: A JSON object containing the username, email, and information about the formations the user is following (formation_follow)
#          and the upcoming formations (pending_session).
@reader.route('/dashboard')
@login_required
def dashboard():
    try:
        infos = db.session.query(User, Book, Session, Follow_session).filter(User.email == current_user.email).join(Follow_session, User.id == Follow_session.user_id).join(Session, Session.id == Follow_session.session_id).join(Book, Book.id == Session.book_id)

        followed_sessions = infos.filter(Session.date < datetime.now()).all()
        pending_sessions = infos.filter(Session.date >= datetime.now(), Follow_session.approved == 0).all()
        current_session_followed = infos.filter(Session.date >= datetime.now(), Follow_session.approved == 1).all()

        followed_sessions_data = []
        for session_follow in followed_sessions:
            followed_sessions_data.append({
                'session_name': session_follow.Session.name,
                'book_title': session_follow.Book.title,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location,
                'date': session_follow.Session.date.strftime('%Y-%m-%d')
            })

        pending_session_data = []
        for pending_session in pending_sessions:
            pending_session_data.append({
                'session_name': pending_session.Session.name,
                'book_title': pending_session.Book.title,
                'author': pending_session.Book.author,
                'location': pending_session.Session.location,
                'date': pending_session.Session.date.strftime('%Y-%m-%d'),
                'approved': pending_session.Follow_session.approved
            })

        current_session_followed_data = []
        for session_follow in current_session_followed:
            current_session_followed_data.append({
                'session_name': session_follow.Session.name,
                'book_title': session_follow.Book.title,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location,
                'date': session_follow.Session.date.strftime('%Y-%m-%d'),
                'approved': session_follow.Follow_session.approved
            })

        return jsonify({
            'username': current_user.username,
            'email': current_user.email,
            'followed_sessions': followed_sessions_data,
            'pending_sessions': pending_session_data,
            'current_session_followed': current_session_followed_data
        })

    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for user logout.
#
# This route is used for user logout. The route is protected, meaning that only a logged-in user can access this route.
# The function logs out the current user using the 'logout_user()' function provided by Flask-Login.
# A JSON object is returned to notify that the user has been successfully logged out.
#
# @return: A JSON object to notify that the user has been successfully logged out.
@reader.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        return jsonify({'message':'You are logged out sucessfully'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for handling forgotten passwords.
#
# This route is used for handling forgotten passwords. The function accepts a POST request with JSON data containing the user's email.
# The function checks if the provided email exists in the database using the 'user_email_exist' function.
# If an account with the provided email exists, a confirmation token is generated for the user.
# A password reset link is created using the confirmation token and sent to the user's email.
# If the email exists and the password reset link is sent successfully, a JSON object with a success message is returned.
# If no account is found with the provided email, a JSON object with an error message is returned.
#
# @param email: The email for receiving the password reset link.
#
# @return: A JSON object containing information about the result of the password reset request.
@reader.route('/forget_password',methods=['POST'])
def forget_password():
    try:
        email=request.json['email']
        if not user_email_exist(email):
            return jsonify({'message':'Any account with this email'}),404
        else:
            confirmation_token=generate_confirmed_token(email)
            confirm_link = f"http://localhost:5000/reader/password_reset/{confirmation_token}"
            #confirmation_email = render_template('proof_your_identity.html',confirm_link=confirm_link)
            msg = Message('Proof your identity', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
            msg.body=confirm_link
            #msg.html = confirmation_email
            mail.send(msg)
            return jsonify({'message':'You have received an confirmation email to proof your identity'}),200
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500

## @brief Route for resetting forgotten passwords for readers.
#
# This route is used for resetting forgotten passwords for readers. The function accepts a POST request with JSON data containing the new password.
# The function takes a 'token' as a parameter, which is used to verify if the password reset link is valid and not expired.
# The 'reader_confirm_token' function checks if the token is valid and returns True if it is, and False otherwise.
# If the token is invalid or expired, a JSON object with an error message is returned.
# If the token is valid and the request method is POST, the function generates a new password hash using the 'bcrypt' library.
# The password hash is updated in the database for the user associated with the email provided in the token.
# A success message is returned to the user indicating that the password has been successfully changed, and the user can now log in with the new password.
#
# @param token: The token contained in the password reset link received by the user's email.
# @param new_password: The new password entered by the user for resetting the forgotten password.
#
# @return: A JSON object containing information about the result of the password reset request.
@reader.route('/password_reset/<token>',methods=['POST'])
def reset_password(token):
    try:
        if not reader_confirm_token(token):
            return jsonify({'message':'Invalid or expired link'}),404
        new_password=request.json['new_password']
        password_hashed=bcrypt.generate_password_hash(new_password)
        user=User.query.filter_by(email=reader_confirm_token(token)).first()
        user.password_hashed=password_hashed
        db.session.commit()
        return jsonify({'message':f'{user.username} ,you have sucessfully changed your password.You can now login'}),200

    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for setting a new username for the current user.
#
# This route is used for setting a new username for the current user. The function accepts a POST request with JSON data containing the user's email, password, and the new username.
# The function checks if the provided email and password match a user in the database using the 'User.query.filter_by' function and the 'bcrypt.check_password_hash' function.
# If the email and password are valid, the function updates the username for the user in the database using the 'db.session.commit()' function.
# A success message is returned to the user indicating that the username has been successfully changed.
# If the email and password are invalid or do not match a user in the database, an error message is returned.
#
# @param password: The password of the current user.
# @param new_username: The new username to be set for the current user.
#
# @return: A JSON object containing information about the result of the request to set the new username.
@reader.route('/set_username',methods=['POST'])
@login_required
def set_username():
    try:
        password=request.json['password']
        new_username=request.json['new_username']

        user=User.query.filter_by(email=current_user.email).first()

        if user and bcrypt.check_password_hash(user.password_hashed,password):
            user.username=new_username
            db.session.commit()
            return jsonify({'message':f'{user.username}'' you have changed your username'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for changing the email of readers.
#
# This route is used for changing the email of readers. The function accepts a POST request with JSON data containing the user's old email, password, and the new email.
# The function checks if the provided old email and password match a user in the database using the 'User.query.filter_by' function and the 'bcrypt.check_password_hash' function.
# If the old email and password are valid, the function updates the email for the user in the database and sets the 'confirmed' attribute to False to indicate that the email needs to be confirmed again.
# A new confirmation token is generated for the new email, and a confirmation email is sent to the new email address using the 'generate_confirmed_token' function and the 'mail.send' function.
# A success message is returned to the user indicating that the email has been successfully changed, and a confirmation email has been sent to the new email address.
# If the old email and password are invalid or do not match a user in the database, an error message is returned.
#
# @param password: The password of the current user to confirm their identity.
# @param new_email: The new email to be set for the current user.
#
@reader.route('/set_email',methods=['POST'])
@login_required
def set_email():
    try:
        old_email=current_user.email
        password=request.json['password']
        new_email=request.json['new_email']

        user=User.query.filter_by(email=old_email).first()

        if user and bcrypt.check_password_hash(user.password_hashed,password):
            user.email=new_email
            user.confirmed=False
            db.session.commit()
            confirmation_token=generate_confirmed_token(new_email)
            confirm_link = f"http://localhost:5000/reader/confirm/{confirmation_token}"
            #confirmation_email = render_template('confirm.html',username=user.username,confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[new_email],sender=ConfigClass.MAIL_USERNAME)
            msg.body=confirm_link
            #msg.html = confirmation_email
            mail.send(msg)
            return jsonify({'message':'You have changed sucessfully your email and  a confirmation email has been sent'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    except Exception as error:
        return jsonify({'message':'Internal serveur error'}),500


## @brief Route for changing passwords for readers.
#
# This route is used for changing passwords for readers. The function accepts a POST request with JSON data containing the user's email, old password, and the new password.
# The function checks if the provided email and old password match a user in the database using the 'User.query.filter_by' function and the 'bcrypt.check_password_hash' function.
# If the email and old password are valid, the function generates a new password hash for the new password using the 'bcrypt.generate_password_hash' function and updates the password hash for the user in the database.
# A success message is returned to the user indicating that the password has been successfully changed.
# If the email and old password are invalid or do not match a user in the database, an error message is returned.
#
# @param old_password: The old password of the current user to confirm their identity.
# @param new_password: The new password to be set for the current user.
#
# @return: A JSON object containing information about the result of the request to change the password.
@reader.route('/set_password',methods=['POST'])
@login_required
def set_password():
    try:
        old_password=request.json['old_password']
        new_password=request.json['new_password']

        user=User.query.filter_by(email=current_user.email).first()

        if user and bcrypt.check_password_hash(user.password_hashed,old_password):
            user.password_hashed=bcrypt.generate_password_hash(new_password)
            db.session.commit()
            return jsonify({'message':f'{user.username} you have changed your password'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    except:
        return jsonify({'message':'Internal server error'}), 500

## @brief Route for deleting a reader's account.
#
# This route allows readers to delete their own accounts. The function accepts a POST request with JSON data containing the user's email and password to confirm their identity.
# The function checks if the provided email and password match the current user's email and password using the 'current_user.email' and 'bcrypt.check_password_hash' functions.
# If the email and password are valid and match the current user's email and password, the function deletes the user's account from the database using the 'db.session.delete' function and commits the changes using the 'db.session.commit' function.
# A success message is returned to the user indicating that their account has been successfully deleted.
# If the email and password are invalid or do not match the current user's email and password, an error message is returned.
#
# @param email: The email of the current user.
# @param password: The password of the current user to confirm their identity.
#
# @return: A JSON object containing information about the result of the request to delete the account.
@reader.route('/delete_account',methods=['POST'])
@login_required
def delete_account():
    try:
        email=current_user.email
        password=request.json['password']
        if current_user.email==email and bcrypt.check_password_hash(current_user.password_hashed,password):
            follow_sessions=Follow_session.query.filter_by(user_id=current_user.id).all()
            follow_packs=Follow_pack.query.filter_by(user_id=current_user.id).all()

            [ db.session.delete(follow_session) for follow_session in follow_sessions ]
            [ db.session.delete(follow_pack) for follow_pack in follow_packs ]
            db.session.commit()

            db.session.delete(current_user)
            db.session.commit()
            return jsonify({'message':'Your account has been  deleted succesfully'}),200
        else:
            return jsonify({'message':f'Invalid email or passsword'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


## @brief Route for registering for a formation.
#
# This route allows users to register for a formation with the given `title`, `author`, and `date`.
# The route checks if a formation exists with the specified details and registers the current user for the formation if found.
# The user's registration is represented by a new entry in the `Follow` table in the database.
# The `follow` attribute for the registration is set to `False` initially.
#
# @return: A JSON object containing a message to notify if the registration is successful or not.
# - 'message': A message indicating the result of the registration process.
# @retval 200: If the registration is successful and the formation is found in the database.
# @retval 404: If the formation is not found in the database.
# @retval 405: If the HTTP method is not allowed (only POST is allowed).
#

@reader.route('/register_session', methods=['POST'])
@login_required
def register_session():
    try:
        token = request.json['id']
        session = db.session.query(Session).filter(Session.token == token).first()
        if session:
            follow = Follow_session(user_id=current_user.id, session_id=session.Session.id)
            db.session.add(follow)
            db.session.commit()
            
            return jsonify({'message': 'You are registered successfully'}), 200
        else:
            return jsonify({'message': 'No session found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/cancel_register_session', methods=['POST'])
@login_required
def cancel_register_session():
    try:
        token=request.json['id']
        
        session=Session.query.filter_by(token=token).first()
        if session:
            follow_session = Follow_session.query.filter_by(user_id=current_user.id, session_id=session.id).first()

            if follow_session:
                db.session.delete(follow_session)
                db.session.commit()
                return jsonify({'message': 'You have successfully canceled your registration for this session'}), 200
            else:
                return jsonify({'message': 'You have not registered for this session'}), 404
        else:
            return jsonify({'message': 'No session found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500
    

@reader.route('/follow_pack', methods=['POST'])
@login_required
def follow_pack():
    try:
        token=request.json['id']
            
        pack=Pack.query.filter_by(token=token).first()
        if pack:
            existing_pack=Follow_pack.query.filter_by(user_id=current_user.id,pack_id=pack.id).first()
            if not existing_pack:
                follow_pack=Follow_pack(user_id=current_user.id,pack_id=pack.id)
                db.session.add(follow_pack)
                db.session.commit()
                return jsonify({'message': 'Pack is successfully added to your pack list'}), 200
            else:
                return jsonify({'message': 'You are alredy followed this pack'}), 200
        else:
            return jsonify({'message': 'Pack not found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/get_followed_pack_list')
@login_required
def get_followed_pack_list():
    try:

        packs=db.session.query(Pack).join(Follow_pack).filter(Pack.id==Follow_pack.pack_id,Follow_pack.user_id==current_user.id)
        
        followed_pack_list=[]
        for followed_pack in packs:
            followed_pack_list.append({'title':followed_pack.title})
        
        if followed_pack_list:
            return jsonify({'followed_pack_list':followed_pack_list}), 200
        else:
            return jsonify({'message': 'You have not followed any pack at the moment'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/unfollowed_pack', methods=['POST'])
@login_required
def unfollowed_pack():
    try:
        token=request.json['id']
        
        pack=Pack.query.filter_by(token=token).first()
        if pack:
            unfollow_pack=db.session.query(Follow_pack).join(Pack).filter(Pack.id==Follow_pack.pack_id,Follow_pack.user_id==current_user.id).first()
            db.session.delete(unfollow_pack)
            db.session.commit()
            return jsonify({'message': 'This pack has been removed from your followed pack list'}), 200
        else:
            return jsonify({'message': 'You are not followed this pack'}), 400
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/apply_for_teacher_job',methods=['POST'])
@login_required
def apply_for_teacher_job():
    try:
        email=current_user.email
        description=request.json['description']
        study_level=request.json['study_level']

        user=User.query.filter_by(email=email).first()

        if user.type=='reader':
            teacher_submit=Teacher_postulate(id=user.id,description=description,study_level=study_level)
            db.session.add(teacher_submit)
            db.session.commit()
            return jsonify({'message':'Your are postulate successfully to the teacher post.You will receive a message when you will accepted'}),200
        else:
            return jsonify({'message':'You are not suscestible to been teacher'}),401
    except:
        return jsonify({'message': 'Internal server error'}), 500


@reader.route('/show_state_of_teacher_job_postulate')
@login_required
def show_state_of_teacher_job_postulate():
    try:
        teacher_submit=Teacher_postulate.query.filter_by(id=current_user.id).first()
        teacher=Teacher.query.filter_by(email=current_user.email).first()

        if teacher_submit:
            if not teacher_submit.selected:
                return jsonify({'message':'Your request treatement is in progress'}),200
        elif teacher:
                return jsonify({'message':'Congratulation you are now teacher'}),200
        else:
            return jsonify({'message':'You hadn\'t postulated to a teacher job or  your request has been rejected'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500



'''

    Followed session

'''