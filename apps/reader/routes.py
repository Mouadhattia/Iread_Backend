## @file
# Blueprint for user readers' authentication.
# Contains routes and functions related to user authentication.
from datetime import datetime
from flask import Blueprint,request,jsonify,render_template, redirect,make_response,session
from flask_bcrypt import Bcrypt
from models.user import User,Reader,Teacher
from models.teacher_postulate import Teacher_postulate
from models.pack import Pack
from models.follow_pack import Follow_pack
from models.Follow_book import Follow_book
from models.book import Book
from models.profile import Profile
from models.book_pack import Book_pack
from models.session import Session
from models.follow_session import Follow_session
from apps.main.email import generate_confirmed_token,reader_confirm_token
from extensions import mail,login_manager,db
from flask_mail import Message
from config import ConfigClass
from flask_login import login_user,logout_user,current_user,login_required
from functools import wraps
import logging
import urllib.request,json,http.cookiejar
from werkzeug.utils import secure_filename
from models.code import Code ,StatusEnum
from models.user_log import UserLog
from geoip2.database import Reader as Beader
import uuid
import requests
import time
from user_agents import parse
from sqlalchemy.orm import aliased
from flask import jsonify
from sqlalchemy import exists, and_
import secrets 






captcha_storage = {}
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

def get_cookies():

    cookie_jar = http.cookiejar.CookieJar()
    cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
    opener = urllib.request.build_opener(cookie_handler)  

    return opener  
def generate_unique_user_id():
    return str(uuid.uuid4())  
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

@reader.route('/register', methods=['POST'])
def register():
    try:
        username = request.json['username']
        email = request.json['email']
        password = request.json['password']

        if user_email_exist(email):
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Make a GET request to obtain the CSRF token
            token_url = f'{ConfigClass.QUIZ_API}user/get_csrf_token'
            token_req = urllib.request.Request(token_url)

            
            opener = get_cookies()
            
            # Perform the GET request with the CookieJar
            token_response = opener.open(token_req)
            response_toekn = json.loads(token_response.read().decode('utf-8'))
            csrf_token = response_toekn.get('csrf_token')

            # Create a new user in your Flask application
            password_hash = bcrypt.generate_password_hash(password)
            new_user = Reader(username=username, email=email, password_hashed=password_hash, created_at=datetime.now())
            db.session.add(new_user)
            

   

                # Send a confirmation email as before
            confirmation_token = generate_confirmed_token(email)
            confirm_link = f"{ConfigClass.API_URL}/reader/confirm/{confirmation_token}"
            confirmation_email = render_template('confirmation_email_template.html', username=username,
                                                      confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
            msg.html = confirmation_email
            mail.send(msg)

            return jsonify({'message': 'Your account has been successfully created. Please verify your emailbox to confirm your account',
                                'user': {'username': username, 'email': email}}), 201
            

    except Exception as error:
        print(str(error))  # Print the error message for debugging
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/google-login', methods=['POST'])
def google_register():
    try:
        username = request.json['username']
        email = request.json['email']
        password = secrets.token_urlsafe(12) 

        if user_email_exist(email):
           google_user=User.query.filter_by(email=email).first()
           login_user(google_user)
           return jsonify({'message':'Your are logged in succesfully','role':google_user.type}),200
        else:
            # Make a GET request to obtain the CSRF token
            token_url = f'{ConfigClass.QUIZ_API}user/get_csrf_token'
            token_req = urllib.request.Request(token_url)   
            opener = get_cookies()
            # Perform the GET request with the CookieJar
            token_response = opener.open(token_req)
            response_toekn = json.loads(token_response.read().decode('utf-8'))
            csrf_token = response_toekn.get('csrf_token')
            # Create a new user in your Flask application
            password_hash = bcrypt.generate_password_hash(password)
            new_user = Reader(username=username, email=email, password_hashed=password_hash, created_at=datetime.now(),confirmed=True,approved=True)
            db.session.add(new_user)
            # Call the external API to register a user and include the CSRF token in the headers
            registration_data = {
                'username': username,
                'email': email,
                'password': password
            }
            registration_data = json.dumps(registration_data).encode('utf-8')
            try:
                url = f'{ConfigClass.QUIZ_API}user/register'
                req = urllib.request.Request(url, data=registration_data, headers={'X-CSRFToken': csrf_token, 'Content-Type': 'application/json'})
                response = opener.open(req)  # Use the opener to include the cookies
                response_data = json.loads(response.read().decode('utf-8'))
                user_id = response_data.get('user', {}).get('id')
                
            except urllib.error.HTTPError as e:
               response_data = json.loads(e.read().decode('utf-8'))
               
               error_message = response_data.get('message', 'Bad Request')
               if error_message =="UNIQUE constraint failed: users_user.username":
                return jsonify({'message': 'User name already exists'}),400
               else : 
                return jsonify({'message': error_message}),400
               
            db.session.commit()
            if user_id is not None:
                # Associate the user_id with the Reader object
                new_user.quiz_id = user_id
                db.session.commit()  
                login_user(new_user)
                return jsonify({'message':'Your are logged in succesfully','role':new_user.type}),200   
            else:
                # Handle the case where registration in the external API failed
                return jsonify({'message': 'Failed to register user in external API'}), 500

    except Exception as error:
        print(str(error))  # Print the error message for debugging
        return jsonify({'message': 'Internal server error'}), 500

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
             return redirect(f"{ConfigClass.FRONT_URL}/authentication/account-confirmed", code=200)
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
            confirm_link = f"{ConfigClass.API_URL}/reader/confirm/{confirmation_token}"
            confirmation_email = render_template('confirmation_email_template.html', username=username, confirm_link=confirm_link)
            msg = Message('Confirm your account', recipients=[email], sender=ConfigClass.MAIL_USERNAME)
            msg.html = confirmation_email
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




@reader.route('/get_cokies', methods=['GET'])
def get_cookies_fun():
    try:
          
        user_id = session.get('user_id')
        if user_id is None:
            user_id = generate_unique_user_id()
            session['user_id']=user_id
            
        
            session['start_time'] = time.time()
            session['log_saved'] = False

            



            user_agent = request.headers.get('User-Agent')
            user_agent_info = parse(user_agent)

            browser = user_agent_info.browser.family
            system = user_agent_info.os.family

            
            user_ip = request.headers.get('X-Forwarded-For')
            if user_ip is None:
                user_ip = request.remote_addr
            referer = request.headers.get('Referer')
            utm_source = request.args.get('utm_source')
            if utm_source:
                source = utm_source
            else:
                source = referer
            user_country = "Unknown"
            user_city = "Unknown"
            with Beader('/var/www/html/Iread_Backend/GeoLite2-City/GeoLite2-City.mmdb') as test:
                try:
                    response = test.city(user_ip)
                    user_country = response.country.name
                    user_city = response.city.name
                except Exception as geo_error:
                    print(f"Error looking up IP: {geo_error}")
            
            user_log = UserLog( user_agent=user_agent, user_ip=user_ip, referer=source,
            user_country=user_country, user_city=user_city,user_cookie_id=user_id,system=system,browser=browser)
            db.session.add(user_log)
            db.session.commit()
            return jsonify({'message': 'Log saved'}), 200
        else:   
            
 
            existing_log = UserLog.query.filter_by(user_cookie_id=user_id).first()
            if existing_log:
                
               
 
                if not session.get('log_saved'):
                   

                    start_time = session.get('start_time')
                    if start_time:
                        end_time = time.time()
                        visit_duration = end_time - start_time

                        existing_log.visit_duration = visit_duration
                        db.session.commit()

                        session['log_saved'] = False

                    return jsonify({'message': 'Returning user, visit duration updated'}), 200

                return jsonify({'message': 'Returning user, log already saved in this session'}), 200
    except Exception as error:
        print(str(error))
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500






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
            return jsonify({'is_authenticated':current_user.is_authenticated,'username':current_user.username,'email':current_user.email,'img':current_user.img,'role':current_user.type,'quiz_id':current_user.quiz_id,'id':current_user.id})
        else:
            return jsonify({'is_authenticated':current_user.is_authenticated}),400
    except Exception as error:
        return jsonify({'message':'Internal serveur error',"error":error}),500


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
        infos = (
            db.session.query(User, Book, Session, Follow_session)
            .filter(User.email == current_user.email)
            .join(Follow_session, User.id == Follow_session.user_id)
            .join(Session, Session.id == Follow_session.session_id)
            .join(Book, Book.id == Session.book_id)
        )

        followed_sessions = infos.filter(
            # Session.start_date < datetime.now()
        ).all()
        pending_sessions = infos.filter(
            # Session.start_date >= datetime.now(),
            Follow_session.approved == 0
        ).all()
        current_session_followed = infos.filter(
            # Session.start_date >= datetime.now(),
            Follow_session.approved == 1
        ).all()

        followed_sessions_data = []
        for session_follow in followed_sessions:
            followed_sessions_data.append({
                'session_name': session_follow.Session.name,
                'id': session_follow.Session.id,
                'book_title': session_follow.Book.title,
                'book_id': session_follow.Book.id,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location.value,
                'date': session_follow.Session.start_date.strftime('%Y-%m-%d'),
                'approved': session_follow.Follow_session.approved,
                'book_img':session_follow.Book.img
            })

        pending_session_data = []
        for pending_session in pending_sessions:
            pending_session_data.append({
                'session_name': pending_session.Session.name,
                'id': pending_session.Session.id,
                'book_title': pending_session.Book.title,
                'book_id': pending_session.Book.id,
                'author': pending_session.Book.author,
                'location': pending_session.Session.location.value,
                'date': pending_session.Session.start_date.strftime('%Y-%m-%d'),
                'approved': pending_session.Follow_session.approved
            })

        current_session_followed_data = []
        for session_follow in current_session_followed:
            current_session_followed_data.append({
                'session_name': session_follow.Session.name,
                'id': session_follow.Session.id,
                'book_title': session_follow.Book.title,
                'book_id': session_follow.Book.id,
                'author': session_follow.Book.author,
                'location': session_follow.Session.location.value,
                'date': session_follow.Session.start_date.strftime('%Y-%m-%d'),
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
        logging.error('An error occurred: %s', error, exc_info=True)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500



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
            confirm_link = f"{ConfigClass.API_URL}/reader/password_reset/{confirmation_token}"
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
            db.session.commit()
            user_info ={
                'username':user.username,
                 'email' :user.email,
                 'img' : user.img,
                 'is_authenticated':user.is_authenticated

            }
           
            return jsonify({'message':'You have changed sucessfully your email','user':user_info}),200
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
            return jsonify({'message':f'Invalid  passsword'}),404
    except Exception as error:
        print(error)
        return jsonify({'message':'something wrong please try  later'}), 500

@reader.route('/set_image',methods=['POST'])
@login_required
def set_image():
    try:
     
        img=request.json['img']

        user=User.query.filter_by(email=current_user.email).first()

        if user  :
            user.img= img
            db.session.commit()
            return jsonify({'message':f'{user.username} you have changed your iamge'}),200
        else:
            return jsonify({'message':f'Invalid  user'}),404
    except Exception as error:
        print(error)
        return jsonify({'message':'something wrong please try  later'}), 500        

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
        
        session_instance = db.session.query(Session).filter(Session.id == token).first()
    
        if session_instance:
            # Assuming session_instance.id is related to pack_id and book_id
            follow_pack = Follow_pack.query.filter_by(pack_id=session_instance.pack_id, user_id=current_user.id).first()
           
            if follow_pack and follow_pack.approved:
                follows_count = Follow_session.query.filter_by(session_id=session_instance.id).count()
                if session_instance.capacity> follows_count:
                    #follow book 
                    follow_book = follow = Follow_book(user_id=current_user.id, book_id=session_instance.book_id ,pack_id=session_instance.pack_id)
                    db.session.add(follow_book)
                    #follow session
                    follow = Follow_session(user_id=current_user.id, session_id=session_instance.id)
                    db.session.add(follow)
                    db.session.commit()
                else :
                    return jsonify({'message': 'Session is Full'}), 404

                return jsonify({'message': 'You are registered successfully'}), 200
            else:
                return jsonify({'message': 'No matching or approved Follow_pack found'}), 404
        else:

            return jsonify({'message': 'No session found'}), 404
    except Exception as e:
        print(e)  # Print the exception for debugging purposes
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
        token = request.json['id']
        code = request.json['code']
        code_to_use = Code.query.filter_by(code=code).first()
        code_id = code_to_use.pack_id
    
        
        if code_to_use:
            if code_id != int(token):
                return jsonify({'message': 'Code does not correspond to the specified pack'}), 400
            if code_to_use.status == StatusEnum.USED:
                return jsonify({'message': 'Code has already been used'}), 400

            # Change code status to 'used' (assuming StatusEnum is an Enum)
            code_to_use.user_id = current_user.id
            code_to_use.status = StatusEnum.USED
            db.session.commit()

            pack = Pack.query.filter_by(id=token).first()
            if pack:
                existing_pack = Follow_pack.query.filter_by(user_id=current_user.id, pack_id=pack.id).first()
                if not existing_pack:
                    follow_pack = Follow_pack(user_id=current_user.id, pack_id=pack.id,approved=True)
                    db.session.add(follow_pack)
                    db.session.commit()

                    followed_pack = {
                        'approved': follow_pack.approved,
                        'id': pack.id,
                        'level': pack.level,
                        'book_number': pack.book_number,
                        'price': pack.price,
                        'title': pack.title
                    }
                    return jsonify({'message': 'Pack is successfully added to your pack list', 'followed_pack': followed_pack}), 200
                else:
                    return jsonify({'message': 'You are already followed this pack'}), 200
            else:
                return jsonify({'message': 'Pack not found'}), 404
        else:
            return jsonify({'message': 'Code not found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500

        
@reader.route('/link_code', methods=['POST'])

def link_code():
    try:
        user_id = request.json['user_id']
        code = request.json['code']
        print(user_id,code)
        code_to_use = Code.query.filter_by(code=code).first()
        user =User.query.filter_by(id=user_id).first()
        print(code_to_use,user)
        if code_to_use :
            if not user :
                return jsonify({'message': 'User not found'}), 400

            # Change code status to 'used' (assuming StatusEnum is an Enum)
            code_to_use.user_id = user_id
            db.session.commit()
            return jsonify({'message': 'Code Linked successfuly'}), 200
        else:
            return jsonify({'message': 'Code not found'}), 404
    except Exception as error:
        return jsonify({'message': 'Internal server error','error':error}), 500


@reader.route('/get_followed_pack_list')
@login_required
def get_followed_pack_list():
    try:
        packs = db.session.query(Pack, Follow_pack.approved).join(Follow_pack).filter(Pack.id == Follow_pack.pack_id, Follow_pack.user_id == current_user.id)

        followed_pack_list = []

        for followed_pack, approved in packs:
            followed_pack_list.append({'title': followed_pack.title, 'id': followed_pack.id, 'approved': approved ,'level':followed_pack.level,'price':followed_pack.price,'book_number':followed_pack.book_number,'img':followed_pack.img})

        if followed_pack_list:
            return jsonify({'followed_pack_list': followed_pack_list}), 200
        else:
            return jsonify({'message': 'You have not followed any pack at the moment'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500

@reader.route('/get_unfollowed_books')
@login_required
def get_unfollowed_books():
    try:
        # Get the packs that the user is following
        followed_packs = db.session.query(Pack, Follow_pack.approved).join(Follow_pack).filter(Pack.id == Follow_pack.pack_id, Follow_pack.user_id == current_user.id)

        unfollowed_books_list = []

        # Iterate through each followed pack
        for followed_pack, approved in followed_packs:
            # Alias for the Follow_book table to avoid conflicts in the join
            follow_book_alias = aliased(Follow_book)
            session_alias = aliased(Session)

            # Get the books in the followed pack that the user has not followed and has a session with a specific book_id
            unfollowed_books = db.session.query(Book, Book_pack, follow_book_alias).join(
                Book_pack,
                Book.id == Book_pack.book_id
            ).outerjoin(
                follow_book_alias,
                and_(
                    follow_book_alias.book_id == Book.id,
                    follow_book_alias.user_id == current_user.id,
                    follow_book_alias.pack_id == followed_pack.id
                )
            ).outerjoin(
                session_alias,
                and_(
                    session_alias.book_id == Book.id,
                   
                )
            ).filter(
                Book_pack.pack_id == followed_pack.id,
                follow_book_alias.book_id.is_(None),
                session_alias.book_id.isnot(None)
            ).all()

            # Append the information to the list
            for book, book_pack, follow_book in unfollowed_books:
                unfollowed_books_list.append({
                    'title': book.title,
                    'book_id': book.id,
                    'pack_id': followed_pack.id,
                    'pack_title': followed_pack.title,
                    'approved': approved,
                    'level': followed_pack.level,
                    'price': followed_pack.price,
                    'book_number': followed_pack.book_number,
                    'img': followed_pack.img
                })

        if unfollowed_books_list:
            return jsonify({'unfollowed_books_list': unfollowed_books_list}), 200
        else:
            return jsonify({'message': 'No unfollowed books found'}), 404
    except Exception as e:
        print(e)
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




@reader.route('/set_profile', methods=['POST'])
@login_required
def create_or_update_profile():
    try:
        existing_profile = Profile.query.filter_by(user_id=current_user.id).first()
        data = request.get_json()
     
        if existing_profile:
            # If a profile with the user_id already exists, update it
            for field in ['first_name', 'last_name', 'phone', 'birth_day', 'address_1', 'address_2', 'state', 'country']:
                if field in data:
                    setattr(existing_profile, field, data[field])
            db.session.commit()
            profile = {
                'user_id': existing_profile.user_id,
                'first_name': existing_profile.first_name,
                'last_name': existing_profile.last_name,
                'phone': existing_profile.phone,
                'birth_day': existing_profile.birth_day,
                'address_1': existing_profile.address_1,
                'address_2': existing_profile.address_2,
                'state': existing_profile.state,
                'country': existing_profile.country
            }
            return jsonify({'message': 'Profile updated successfully','profile':profile})
        else:
            # If no profile with the user_id exists, create a new one
            new_profile = Profile(user_id=current_user.id)
            
            # Update only the fields that are present in the JSON data
            for field in ['first_name', 'last_name', 'phone', 'birth_day', 'address_1', 'address_2', 'state', 'country']:
                if field in data:
                    setattr(new_profile, field, data[field])
            
            db.session.add(new_profile)

            profile = {
                'user_id': new_profile.user_id,
                'first_name': new_profile.first_name,
                'last_name': new_profile.last_name,
                'phone': new_profile.phone,
                'birth_day': new_profile.birth_day,
                'address_1': new_profile.address_1,
                'address_2': new_profile.address_2,
                'state': new_profile.state,
                'country': new_profile.country
            }
            db.session.commit()
            return jsonify({'message': 'Profile created or updated successfully','profile':profile}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@reader.route('/my__profile', methods=['GET'])
@login_required
def get_profile():
    try:
        profile = Profile.query.filter_by(user_id=current_user.id).first()
        if profile:
            return jsonify({
                'user_id': profile.user_id,
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'phone': profile.phone,
                'birth_day': profile.birth_day,
                'address_1': profile.address_1,
                'address_2': profile.address_2,
                'state': profile.state,
                'country': profile.country
            })
        else:
            return jsonify({'message': 'Profile not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


        # get quiz

@reader.route('/get_all_quizs', methods=['GET'])
def get_quizs():
    try:

        url = f'{ConfigClass.QUIZ_API}quiz/quiz-list'
        req = urllib.request.Request(url) 
        response = urllib.request.urlopen(req)
        response_data = json.loads(response.read().decode('utf-8'))
        quizs = response_data  
        
        return jsonify(quizs)
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/start_quiz', methods=['POST'])
def start_quizs():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/start-quiz/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/first_question', methods=['POST'])
def first_question():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/first-question/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    question_id=data['question_id']
    user_answer =data['user_answer']

    registration_data = {
        'user_id': user_id,
        'user_answer':user_answer,
        'question_id':question_id

    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/submit/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/result', methods=['POST'])
def result():
    data = request.get_json()
    user_id = data['user_id']
    token = data['token']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/result/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/assigned', methods=['POST'])
def assigned():
    data = request.get_json()
    user_id = data['user_id']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/assignment'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400

@reader.route('/teacher_quiz', methods=['POST'])
def teacher_quiz():
    data = request.get_json()
    user_id = data['user_id']
    registration_data = {
        'user_id': user_id,
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/teacher_quiz'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400



@reader.route('/quiz_by_token', methods=['POST'])
def quiz_by_token():
    data = request.get_json()
    token = data['token']
    registration_data = {
        'token': token,
    }
    try:
        url = f'{ConfigClass.QUIZ_API}quiz/quiz-by-token'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        response_data = json.loads(response.read().decode('utf-8'))
        quiz = response_data 
        return jsonify(quiz)

    except urllib.error.HTTPError as e:
        # Handle HTTP errors (e.g., 404, 500) here
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print("API Error:", error_message)
        return jsonify({'message': error_message}), e.code
    except Exception as ex:
        # Handle other exceptions here
        print("Exception:", ex)
        return jsonify({'message': 'Internal Server Error'}), 500



@reader.route('/assign_quiz_to_user', methods=['POST'])
def assign_quiz_to_user():
    data = request.get_json()
    assigned_by = data['assigned_by']
    email =data['email']
    quiz_token =data['quiz_token']

    registration_data = {
        'assigned_by': assigned_by,
        'email': email,
        'quiz_token':quiz_token
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/assign_quiz_to_user'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 201:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400


@reader.route('/get-essay-answer', methods=['POST'])
def get_essay_answer():
    data = request.get_json()
    token = data['token']
    user_id =data['user_id']
  

    registration_data = {
        'user_id': user_id,   
    }
    try:
        
        url = f'{ConfigClass.QUIZ_API}quiz/get-essay-answer/{token}'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400     

@reader.route('/validate-essay-answer', methods=['POST'])
def validate_essay_answer():
    data = request.get_json()
    answer_token =data['answer_token']
    teacher_approval = data['teacher_approval']
    teacher_comments =data['teacher_comments']
    teacher_checked =data['teacher_checked']
    score =data['score']
    user_id =data['user_id']
  

    registration_data = {
        'user_id': user_id,   
        'answer_token':answer_token,
        'teacher_approval':teacher_approval,
        'teacher_comments':teacher_comments,
        'teacher_checked':teacher_checked,
        'score':score

    }
    print(registration_data)
    try:
        
        url = f'{ConfigClass.QUIZ_API}user/validate-essay-answer'
        req = urllib.request.Request(url, data=json.dumps(registration_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        if response.status == 200:
            response_data = json.loads(response.read().decode('utf-8'))
            quiz = response_data 
            return jsonify(quiz)
        else:
            print(f"API Error: {response.status} - {response.reason}")
            return jsonify({'error': 'An error occurred during the API request'})
    except urllib.error.HTTPError as e:
        response_data = json.loads(e.read().decode('utf-8'))
        error_message = response_data.get('message', 'Bad Request')
        print(error_message )
        return jsonify({'message': error_message}),400   

from flask import request, jsonify
import urllib.request
import json

@reader.route('/import-quiz-json', methods=['POST'])
def import_quiz_json():
    try:
        # Check if the request contains a file
        if 'json_file' not in request.files:
            return jsonify({'error': 'No JSON file provided'}), 400

        jsonFile = request.files['json_file']

        try:
            url = f'{ConfigClass.QUIZ_API}quiz/import-quiz'
            files = {'json_file': (jsonFile.filename, jsonFile.stream, 'application/json')}
            
            response = requests.post(url, files=files)

            if response.status_code == 201:
                response_data = response.json()
                quiz = response_data
                return jsonify(quiz)
            else:
                print(f"API Error: {response.status_code} - {response.reason}")
                return jsonify({'error': 'An error occurred during the API request'})
        except requests.exceptions.HTTPError as e:
            response_data = e.response.json()
            error_message = response_data.get('message', 'Bad Request')
            print(error_message)
            return jsonify({'message': error_message}), 400

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500






'''




    Followed session

'''