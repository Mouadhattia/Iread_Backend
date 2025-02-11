## @file
# Blueprint for user readers' management.
# Contains routes and functions related to reader management.

from uuid import uuid4

from flask import Blueprint,jsonify,abort,render_template,request
from flask_login import logout_user,login_required,current_user
from extensions import login_manager,mail,db
from flask_bcrypt import Bcrypt
from models.user import User,Reader,Teacher,Admin,Assistant
from models.book_pack import Book_pack
from models.shcool import Shcool
from models.book import Book
from models.unit import Unit
from models.user_shcool import User_shcool
from models.Follow_book import Follow_book
from models.user_log import UserLog
from models.session import Session,Location
from models.pack_template import Pack_template
from models.pack import Pack
from models.code import Code ,StatusEnum
from models.follow_session import Follow_session
from models.teacher_postulate import Teacher_postulate
from models.follow_pack import Follow_pack
from models.session_quiz import Session_quiz
from models.about_book import About_Book
from models.book_text import Book_text
from models.notification_user import Notification_user
import logging
import requests
from apps.main.email import generate_confirmed_token
from config import ConfigClass
from flask_mail import Message
from functools import wraps
from datetime import datetime
from sqlalchemy import func
from apps.main.email import admin_confirm_token
import secrets
import string
import json
import webcolors
import random
import spacy
from apps.admin.paserStory import get_tenses_words
from apps.admin.graphDBscripts.db import Neo4jDriver,DataSetDB
import nltk
from nltk.corpus import wordnet
from googletrans import Translator

translator = Translator()
## @brief Decorator to enforce admin access for a view function.
#
# This decorator checks if the current user is an admin before allowing access to the decorated view function.
# If the current user is not an admin, the function returns a 404 error using the 'abort' function.
#
# @param f: The view function to be decorated.
# @return: The decorated function that enforces admin access.
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.type!='admin':
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function

def user_email_exist(email):
    user=User.query.filter_by(email=email).first()
    if user :
        return True
    else:
        return False


def get_short_definition(word):
    try:
        synsets = wordnet.synsets(word)
        if synsets:
            return synsets[0].definition()  # Return the first definition
        return "Definition not found."
    except Exception as e:
        return f"Error: {str(e)}"


def translate_to_arabic(text):
    try:
        translation = translator.translate(text, src='en', dest='ar')
        return translation.text
    except Exception as e:
        return f"Translation error: {str(e)}"
## @brief Creation of the blueprint for user management by administrators.
#
# This blueprint defines routes and views for managing users by administrators.
# The blueprint is registered with the URL prefix '/admin'.
admin=Blueprint('admin',__name__,url_prefix='/admin')
bcrypt=Bcrypt()
login_manager.init_app(admin)

## @brief User loader function for login manager.
#
# This function is used by the login manager to load users from the SQL database.
# It takes a unique user ID as input and returns the corresponding user object.
#
# @param user_id: The unique identifier of the user.
# @return: The user object with the specified ID.
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



## @brief Route to the admin dashboard to view their profile.
#
# This route is used by administrators to access their dashboard and view their profile details.
# The response is a JSON object containing the administrator's username and email.
#
# @return: A JSON object containing the administrator's username and email.
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    return jsonify({'email':current_user.email,'username':current_user.username}),200



## @brief Route to invite a reader to become an administrator.
#
# This route is used by administrators to invite a reader to become an administrator.
# The route accepts a POST request with JSON data containing the reader's email and username.
# The function generates a new confirmation token for the reader, sends an email invitation,
# and returns a JSON object containing a message indicating the success of the invitation.
#
# @param email: Email of the reader for sending the confirmation link.
# @param username: Username of the reader being invited.
# @return: A JSON object containing a message notifying if the invitation was successful or not.
@admin.route('/invite_admin',methods=['POST'])
@login_required
@admin_required
def invite_admin():
    try:
        email=request.json['email']
        username=request.json['username']
        confirmation_token=generate_confirmed_token(email)
        confirm_link = f"http://localhost:5000/admin/confirm/{confirmation_token}"
        #confirmation_email = render_template('invite_admin.html',username=username,confirm_link=confirm_link)
        msg = Message('Invitation to get admin\'s roles', recipients=[email],sender=ConfigClass.MAIL_USERNAME)
        msg.body=confirm_link
        #msg.html = confirmation_email
        mail.send(msg)

        return jsonify({'message':'Admin invited sucessfully'}),200
    except Exception:
        return jsonify({'message':'Internal server error'}),500


## @brief Route for confirming administrator privileges from the received email.
#
# This route is used for confirming administrator privileges based on the confirmation token
# received in the email sent to the user. If the link is valid and not expired, the 'is_admin'
# attribute of the user is set to 1 (True) to grant administrator privileges.
#
# @param token: Token extracted from the confirmation email sent to the user.
# @return: A JSON object indicating whether the confirmation was successful or not.
@admin.route('/confirm/<token>')
def confirm(token):
    try:
        admin_confirm_token(token)
    except Exception:
        return jsonify({'message':'Invalid or exprired link'}),404

    return jsonify({'message':'Congratulation you are now admin'}),200


## @brief Route to display information about all users.
#
# This route is used by administrators to retrieve information about all users in the system.
# The response is a JSON object containing various user details such as email, username, confirmation status, and admin status.
#
# @return: A JSON object containing information about all users.
@admin.route('/show_all_readers')
# @login_required
# @admin_required
def show_all_readers():
    try:


        # Retrieve all reader IDs associated with current user's school ID
        user_school = User_shcool.query.filter_by(user_id=current_user.id).first()
        user_shcools = User_shcool.query.filter_by(shcool_id=user_school.shcool_id).all()
        # Extract reader IDs associated with the school
        reader_ids = [user.user_id for user in user_shcools]
        # Retrieve reader data for the extracted IDs
        reader_data = []
        for reader_id in reader_ids:
            
            reader = User.query.get(reader_id)
            if reader.type=="reader":  
                reader_data.append({
                    'email': reader.email,
                    'username': reader.username,
                    'confirmed': reader.confirmed,
                    'id': reader.id,
                    'img': reader.img,
                    'approved': reader.approved,
                    'quiz_id': reader.quiz_id
                })
        return jsonify({
            'readers': reader_data
        }), 200


    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/followers/<int:pack_id>', methods=['GET'])
def get_users_following_pack(pack_id):
    """
    Get all users who follow a specific pack by pack_id.
    """
    try:
        # Query to get the User details for the given pack_id
        followers = (
            db.session.query(User)
            .join(Follow_pack, Follow_pack.user_id == User.id)
            .filter(Follow_pack.pack_id == pack_id)
            .all()
        )

        # Create a response with user details
        follower_details = [
            {
                'email': follower.email,
                'username': follower.username,
                'confirmed': follower.confirmed,
                'id': follower.id,
                'img': follower.img,
                'approved': follower.approved,
                'quiz_id': follower.quiz_id
            }
            for follower in followers
        ]

        return jsonify({'readers': follower_details}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# get all teachers
@admin.route('/show_all_teachers')
# @login_required
# @admin_required
def show_all_teachers():
    try:
        # Retrieve the school associated with the current user
        user_school = User_shcool.query.filter_by(user_id=current_user.id).first()
        # If user_school is None, handle the case where the current user doesn't have a school assigned

        # Retrieve all user_shcools associated with the school
        user_shcools = User_shcool.query.filter_by(shcool_id=user_school.shcool_id).all()
        
        # Extract user IDs associated with the school
        user_ids = [user.user_id for user in user_shcools]

        # Retrieve all teachers
        # Collect user data associated with each teacher's ID
        user_data = []
        for user_id in user_ids:     
            user = User.query.filter_by(id=user_id, type="teacher").first()
            if user:
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img': user.img,
                    'approved': user.approved,
                    'quiz_id': user.quiz_id
                })

        return jsonify({
            'teachers': user_data
        }), 200
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/show_all_assistants')
# @login_required
# @admin_required
def show_all_assistants():
    try:
        user_school = User_shcool.query.filter_by(user_id=current_user.id).first()
        user_shcools = User_shcool.query.filter_by(shcool_id=user_school.shcool_id).all()
        user_ids = [user.user_id for user in user_shcools]
        user_data = []
        for user_id in user_ids: 
            user = User.query.filter_by(id=user_id,type="assistant").first()
            if user:

                    
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img':user.img,
                    'approved':user.approved,
                    'quiz_id':user.quiz_id
                    })

        return jsonify({
            'assistans': user_data
        }), 200
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error','error':e}), 500

@admin.route('/get_user/<int:user_id>', methods=['GET'])

# @login_required
# @admin_required
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if user:
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'confirmed': user.confirmed,
                'created_at': user.created_at,
                'type': user.type,
                'img':user.img
            }

            if user.type == 'teacher':
                teacher = Teacher.query.filter_by(id=user.id).first()
                if teacher:
                    user_data['description'] = teacher.description
                    user_data['study_level'] = teacher.study_level

            return jsonify(user_data), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/update_user', methods=['PUT'])
# @login_required
# @admin_required
def update_user():
    try:
        data = request.json
        user_id = data.get('id')

        user = User.query.get(user_id)
        if user:
            if 'username' in data:
                user.username = data['username']

            if 'img' in data:
                user.img = data['img']
            
            if 'email' in data:
                new_email = data['email']
                accounts= User.query.filter(User.email == new_email).all()
                
                # Check if the new email is already in use
                if len(accounts)>=3:
                    return jsonify({'message': 'You reached the limit of accounts (3)'}), 400
                user.email = new_email
            if 'quiz_id' in data :
                user.quiz_id =data['quiz_id']    
            if 'password' in data:
                if data['password'] != "":
                    user.password_hashed = bcrypt.generate_password_hash(data['password'])
                else:
                    return jsonify({'message': 'Password cannot be empty'}), 400 

            # Assuming you're using some sort of database session management, commit the changes
            db.session.commit()
            response_data = {
                'message': 'Reader updated successfully',
                'teacher': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'img': user.img,
                    'approved': user.approved,
                }
            }
            return jsonify(response_data), 200  # OK
        else:
            return jsonify({'message': 'Invalid id'}), 404
    except Exception as e:
        return jsonify({'message': 'Internal server error'}), 500





@admin.route('/create_user',methods=['POST'])
# @login_required
# @admin_required
def create_user():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        img =data['img']


        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Hash the password
            password_hash = bcrypt.generate_password_hash(password)
             #Create a new user in quiz api
            quiz_user ={
                'app':f'{ConfigClass.QUIZ_API_KEY}'
            }
            invoicing_client ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}'
            }
            invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/client/create', json=invoicing_client)  
            response = requests.post(ConfigClass.QUIZ_API, json=quiz_user)  

            if response.status_code == 201 and invoicing_response.status_code==201:
                quiz_id = response.json()['_id']
                client_id = invoicing_response.json()['_id']
                
                # Create a new user
                new_user = Reader(
                    img=img,
                    username=username,
                    email=email,
                    password_hashed=password_hash,
                    created_at=datetime.now(),
                    confirmed=True,
                    quiz_id=quiz_id,
                    client_id_invoicing_api=client_id
                    )

                # Add the user to the database
                db.session.add(new_user)
                db.session.commit()
                shcool=  User_shcool.query.filter_by(user_id=current_user.id).first() 
                new_user_shcool = User_shcool(
                  user_id = new_user.id,
                  shcool_id = shcool.shcool_id
                )
                db.session.add(new_user_shcool)
                db.session.commit()

            # Return a success response
            response_data = {
                'message': 'Your account has been successfully created.',
                'user': {
                    'username': username,
                    'email': email,
                    'confirmed': new_user.confirmed,
                    'id': new_user.id,
                    'img':new_user.img,
                    'quiz_id':new_user.quiz_id
                  
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/create_assistant', methods=['POST'])
# @login_required
# @admin_required
def create_assistant():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        img = data['img']

       
        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:

            invoicing_user = {'appId': f'{ConfigClass.INVOICING_API_KEY}'}
            invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/user/create', json=invoicing_user)  
            if invoicing_response.status_code == 201:
                
                user_id = response.json()['_id']
                # Hash the password
                password_hash = bcrypt.generate_password_hash(password)

                # Create a new user
                new_user = Assistant(
                    img=img,
                    username=username,
                    email=email,
                    password_hashed=password_hash,
                    created_at=datetime.now(),
                    confirmed=True,
                    approved=True,
                    user_id_invoicing_api=user_id
                )
                # Add the user to the database
                db.session.add(new_user)
                db.session.commit()
                shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
                new_user_shcool = User_shcool(
                    user_id = new_user.id,
                    shcool_id = shcool.shcool_id
                    )
                db.session.add(new_user_shcool)
                db.session.commit()

                # Return a success response
                response_data = {
                    'message': 'Your account has been successfully created.',
                    'user': {
                        'username': username,
                        'email': email,
                        'confirmed': new_user.confirmed,
                        'id': new_user.id,
                        'img': new_user.img
                    }
                }    
                return jsonify(response_data), 201
            else:
                password_hash = bcrypt.generate_password_hash(password)

                # Create a new user
                new_user = Assistant(
                    img=img,
                    username=username,
                    email=email,
                    password_hashed=password_hash,
                    created_at=datetime.now(),
                    confirmed=True,
                    approved=True
                    
                )
                # Add the user to the database
                db.session.add(new_user)
                db.session.commit()
                shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
                new_user_shcool = User_shcool(
                    user_id = new_user.id,
                    shcool_id = shcool.shcool_id
                    )
                db.session.add(new_user_shcool)
                db.session.commit()

                # Return a success response
                response_data = {
                    'message': 'Your account has been successfully created.',
                    'user': {
                        'username': username,
                        'email': email,
                        'confirmed': new_user.confirmed,
                        'id': new_user.id,
                        'img': new_user.img
                    }
                }    
                return jsonify(response_data), 201
                 
                 
    except Exception as e:
        
        # Handle exceptions and return an error response
        return jsonify({'message': e}), 500





@admin.route('/create_teacher',methods=['POST'])
# @login_required
# @admin_required
def create_teacher():
    try:
        # Get data from the request
        data = request.get_json()
        username = data['username']
        email = data['email']
        password = data['password']
        description = data['description']
        study_level = data['study_level']
        img =data['img']

        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Hash the password
            password_hash = bcrypt.generate_password_hash(password)

            # Create a new user
            new_user = Teacher(
                img=img,
                username=username,
                email=email,
                password_hashed=password_hash,
                created_at=datetime.now(),
                description =description,
                study_level= study_level,
                confirmed=True,
               
            )

            # Add the user to the database
            db.session.add(new_user)
            db.session.commit()
            shcool=  User_shcool.query.filter_by(user_id=current_user.id).first()
            new_user_shcool = User_shcool(
                user_id = new_user.id,
                shcool_id = shcool.shcool_id
                )
            db.session.add(new_user_shcool)
            db.session.commit()
            # Return a success response
            response_data = {
                'message': 'Your account has been successfully created.',
                'user': {
                    'username': username,
                    'email': email,
                    'confirmed': new_user.confirmed,
                    'id': new_user.id,
                    'img':new_user.img,
                    'description' :new_user.description,
                    'study_level' : new_user.study_level

                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        # Handle exceptions and return an error response
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/update_teacher', methods=['PUT'])
# @login_required
# @admin_required

def update_teacher():
    data = request.json
    teacher_id = data.get('id')
    try:
        # Get the teacher by their ID
        teacher = Teacher.query.get(teacher_id)

        if not teacher:
            return jsonify({'message': 'Teacher not found'}), 404  # Not Found

        # Get data from the request

        # You can update any fields you want here
        if 'username' in data:
            teacher.username = data['username']
        if 'email' in data:
            new_email = data['email']
            # Check if the new email is already in use
            if Teacher.query.filter(Teacher.email == new_email, Teacher.id != teacher_id).first():
                return jsonify({'message': 'Email is already in use'}), 400
            teacher.email = new_email
        if 'password' in data:
            # Hash the new password
            teacher.password_hashed = bcrypt.generate_password_hash(data['password'])
        if 'description' in data:
            teacher.description = data['description']
        if 'study_level' in data:
            teacher.study_level = data['study_level']
        if 'img' in data:
            teacher.img = data['img']    

        # Commit the changes to the database
        db.session.commit()

        # Return a success response
        response_data = {
            'message': 'Teacher updated successfully',
            'teacher': {
                'id': teacher.id,
                'username': teacher.username,
                'email': teacher.email,
                'img': teacher.img,
                'description': teacher.description,
                'study_level': teacher.study_level,
                'approved': teacher.approved
            }
        }
        return jsonify(response_data), 200  # OK

    except Exception as e:
        # Handle exceptions and return an error response
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/approved_user',methods=['POST'])
# @login_required
# @admin_required
def approved_user():
    try:
        id=request.json['id']
        user=User.query.filter_by(id=id).first()
        if user:

            user.approved=True
            user.confirmed =True
            db.session.commit()
            return jsonify({'message':'Account approved sucessfully'}),200

        else :
            return jsonify({'message':'Invalid id'}),404
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

## @brief Route to delete a user's account.
#
# This route is used by administrators to delete a user's account based on the email provided.
# The function accepts a POST request with JSON data containing the user's email to be deleted.
# If the user with the specified email exists, their account will be deleted from the database.
#
# @param email: The email of the user whose account needs to be deleted.
# @return: A JSON object indicating whether the account deletion was successful or not.
@admin.route('/delete_user',methods=['POST'])
# @login_required
# @admin_required
def delete_user():
    try:
        id = request.json['id']
        user = User.query.get(id)
        
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify({'message': 'Account deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid ID'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


## @brief Route to revoke administrator roles from another administrator.
#
# This route is used by administrators to revoke administrator roles from another administrator based on the email provided.
# The function accepts a POST request with JSON data containing the email of the other administrator whose roles need to be revoked.
# If the user with the specified email exists and is an administrator, their 'is_admin' attribute will be set to False,
# removing their administrator rights.
#
# @param email: The email of the other administrator whose roles need to be revoked.
# @return: A JSON object indicating whether the operation was successful or not.
@admin.route('/revoke_admin_roles',methods=['POST'])
@login_required
@admin_required
def revoke_admin_roles():
    try:
        email=request.json['email']
        admin=Admin.query.filter_by(email=email).first()
        if admin:

            follow_session=Follow_session.query.filter_by(user_id=admin.id).first()
            follow_pack=Follow_pack.query.filter_by(user_id=admin.id).first()
            #a revoir
            db.session.delete(follow_session) if follow_session else None
            db.session.delete(follow_pack) if follow_pack else None
            db.session.commit()

            reader=Reader(id=admin.id,username=admin.username,email=email,password_hashed=admin.password_hashed)
            db.session.delete(admin)
            db.session.commit()
            db.session.add(reader)
            db.session.commit()
            return jsonify({'message':'Admin\'s roles revoked succesfully'}),200
        else:
            return jsonify({'message':'Invalid email'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500
        

## @brief Route for administrator logout.
#
# This route is used by administrators to log out from the system.
# After successful logout, the function returns a JSON object indicating that the logout was successful.
#
# @return: A JSON object notifying if the logout was successful.
@admin.route('/logout')
@login_required
@admin_required
def logout():
    logout_user()
    return jsonify({'message':'You are logged out sucessufully'}),200


## @brief Route for creating a new formation.
#
# This route is used by administrators to create a new formation based on the data provided in the request.
# The function accepts a POST request with JSON data containing the title, author, place, and date of the formation.
# The formation is then added to the database.
#
# @param title: Title of the book associated with the formation.
# @param author: Author of the book associated with the formation.
# @param place: Location of the formation, which can be 'online' or 'classroom'.
# @param date_str: Date of the formation in the format 'YYYY-MM-DD'.
#
# @return: A JSON object indicating whether the formation creation was successful or not.


# Get all sessions


def generate_random_color():
    # Generate a random RGB color code
    rgb_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    # Convert the RGB color to a hex color code
    hex_color = webcolors.rgb_to_hex(rgb_color)

    return hex_color

@admin.route('/sessions', methods=['GET'])
def get_sessions():
    sessions = Session.query.all()
    session_list = []
    
    teacher_color_mapping = {}  # Dictionary to store teacher colors

    for session in sessions:
        teacher_id = session.teacher_id
        teacher = Teacher.query.get(teacher_id)

        # Handle the case where teacher is None
        if not teacher:
            teacher_name = "Unknown Teacher"
            teacher_color = "#000000"  # Default color for unknown teacher
        else:
            # Check if the teacher already has a color assigned
            if teacher_id not in teacher_color_mapping:
                # Generate a random color for the current teacher
                teacher_color_mapping[teacher_id] = generate_random_color()

            # Use the color associated with the current teacher
            teacher_color = teacher_color_mapping[teacher_id]
            teacher_name = teacher.username

        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': teacher_id,
            'teacher_name': teacher_name,
            'teacher_color': teacher_color,
            'location': session.location.value,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active,
            'unit_id': session.unit_id
        })

    return jsonify({'sessions': session_list}), 200


# get session by teacher
@admin.route('/sessions_by_teacher/<int:teacher_id>', methods=['GET'])
def get_sessions_by_teacher(teacher_id):
    sessions = Session.query.filter_by(teacher_id=teacher_id).all()
    session_list = []

    for session in sessions:
        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': session.teacher_id,
            'location': session.location.value,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active
        })

    return jsonify({'sessions': session_list}), 200

# get  reader in session 
@admin.route('/reader_in_session/<int:session_id>', methods=['GET'])
def reader_in_session(session_id):
    try:
        session_follow_requests = Follow_session.query.filter_by(session_id=session_id, approved=True).all()
        
        all_session = []
        for follow_request in session_follow_requests:
            user_info = User.query.get(follow_request.user_id)
            all_session.append({

                'user_id': user_info.id,
                'username': user_info.username,
                'email': user_info.email,
                'img' : user_info.img,
                'quiz_id':user_info.quiz_id,
                'presence':follow_request.presence
            })

        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/user_session/<string:code>', methods=['GET'])
def user_session(code):
    try:
        print(code)
        user_code = Code.query.filter_by(code=code).first()
        user = User.query.filter_by(id=user_code.user_id).first()
        print(user.id)
        session_follow_requests = Follow_session.query.filter_by(user_id=user.id).all()
       
        all_session = []
        
        for follow_request in session_follow_requests:
            session =Session.query.get(follow_request.session_id)
            # print(session)
            all_session.append({
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'img' : user.img,
                'quiz_id':user.quiz_id,
                'start_date':session.start_date,
                'end_date':session.end_date,
                'name':session.name,
                'presence':follow_request.presence
            })
        print(all_session )
        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error','error':e}), 500



@admin.route('/reader_in_pack/<int:pack_id>', methods=['GET'])
def reader_in_pack(pack_id):
    try:
        pack_follow_requests = Follow_pack.query.filter_by(pack_id=pack_id).all()
        
        user_in_pack = []
        for follow_request in pack_follow_requests:
            user_info = User.query.get(follow_request.user_id)
            user_in_pack.append({

                'user_id': user_info.id,
                'username': user_info.username,
                'email': user_info.email,
                'img' : user_info.img,
                'quiz_id':user_info.quiz_id,
                'presence':follow_request.presence
            })

        return jsonify({'user_in_pack': user_in_pack}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



#update presence 
@admin.route('/update_presence/<int:session_id>/<int:user_id>', methods=['PUT'])
def update_presence(session_id, user_id):
    try:
        # Get the request data
        data = request.get_json()

        # Check if the 'presence' field is provided in the request data
        if 'presence' in data:
            presence = data['presence']

            # Find the Follow_session record for the specified session and user
            follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

            if follow_request:
                # Update the 'presence' field
                follow_request.presence = presence
                db.session.commit()

                return jsonify({'message': 'Presence updated successfully'}), 200
            else:
                return jsonify({'message': 'Follow_session record not found for the specified session and user'}), 404
        else:
            return jsonify({'message': 'Please provide the "presence" field in the request data'}), 400

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


# Define the route to get sessions by book_id from request body
@admin.route('/sessions_in_book', methods=['POST'])
def get_sessions_by_book_id_from_body():
    data = request.get_json()
    
    # Check if the 'book_id' key exists in the JSON request body
    if 'book_id' not in data:
        return jsonify({'message': 'The request must contain a "book_id" field in the JSON body'}), 400

    book_id = data['book_id']

    # Query sessions with the specified book_id
    sessions = Session.query.filter_by(book_id=book_id).all()
    
    # Check if sessions were found
    if not sessions:
        return jsonify({'message': 'No sessions found for book_id {}'.format(book_id)}), 404
    
    # Create a list to store session information
    session_list = []

    for session in sessions:
        teacher = Teacher.query.filter_by(id=session.teacher_id).first()
        book = Book.query.filter_by(id=session.book_id).first()

        session_list.append({
            'id': session.id,
            'name': session.name,
            'capacity': session.capacity,
            'book_id': session.book_id,
            'teacher_id': session.teacher_id,
            'location': session.location.value,
            'start_date': session.start_date,
            'end_date': session.end_date,
            'pack_id': session.pack_id,
            'description': session.description,
            'active': session.active,
            'book_name' : book.title,
             'teacher_name' : teacher.username

        })

    return jsonify({'sessions': session_list}), 200

# Create a new session
@admin.route('/create_session', methods=['POST'])
def create_session():
    try:

        data = request.get_json()
        unit_id = None

        # Validate required fields
        required_fields = ['name', 'start_date','end_date','unit']
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400   
        exist_session=Session.query.filter_by(name=data['name']).first()
        teacher = Teacher.query.filter_by(id=data['teacher_id']).first()
        book = Book.query.filter_by(id=data['book_id']).first()
        exist_unit=Unit.query.filter_by(name=data['unit'],book_id=data['book_id']).first()
        if exist_unit:
            unit_id =exist_unit.id
        else:
            new_unit=Unit(name=data['unit'],book_id=data['book_id'])
            db.session.add(new_unit)
            db.session.commit()
            unit_id= new_unit.id
        if exist_session :
            return jsonify({'message':'Session name already exist'}),404
        else:
             new_session = Session(
             name=data['name'],
             capacity=data['capacity'],
             book_id=data['book_id'],
             teacher_id=data['teacher_id'],
             location=data['location'],
             start_date=data['start_date'],
             end_date=data['end_date'],
             pack_id=data['pack_id'],
             description=data['description'],
             active=data['active'],
             unit_id=unit_id
            )
    
        db.session.add(new_session)
        db.session.commit()
        session_info = {

             'id': new_session.id,
             'name': new_session.name,
             'capacity': new_session.capacity,
             'book_id': new_session.book_id,
             'teacher_id': new_session.teacher_id,
             'location': new_session.location.value,
             'start_date': new_session.start_date,
             'end_date': new_session.end_date,
             'pack_id': new_session.pack_id,
             'description': new_session.description,
             'active': new_session.active,
             'book_name' : book.title,
             'teacher_name' : teacher.username
             }

        return jsonify({'message': 'Session created successfully','session':session_info}), 201
    
    except Exception as e:
        print(e)
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

#get session numbers 
@admin.route('/session_count', methods=['POST'])
def count_sessions():
    try:
        book_id = request.json['book_id']
        pack_id = request.json['pack_id']
        # Get the session related with pack bok 
        sessions = Session.query.filter_by(book_id=book_id,pack_id=pack_id).count()
        return jsonify({'session_number':sessions})


    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500    



@admin.route('/delete_session', methods=['POST'])
def delete_session():
    try:
        token = request.json['id']
        # Get the session to be deleted
        session = Session.query.filter_by(id=token).first()
        if session:
            # Delete all associated records in Follow_session table
            follow_sessions = Follow_session.query.filter_by(session_id=session.id).all()
            for follow in follow_sessions:
                db.session.delete(follow)
            # Delete all associated records in Session_quiz table
            session_quizzes = Session_quiz.query.filter_by(session_id=session.id).all()
            for session_quiz in session_quizzes:
                db.session.delete(session_quiz)
            # Commit the changes
            db.session.commit()
            # Delete the session
            db.session.delete(session)
            db.session.commit()

            return jsonify({'message': 'Session and associated records successfully deleted'})
        else:
            return jsonify({'message': 'No matching session found'})
    except Exception as e:
        print(e)
        return jsonify({'message': 'Internal server error'}), 500


# Get a specific session by ID
@admin.route('/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id):
    session = Session.query.get(session_id)

    if session is None:
        return jsonify({'message': 'Session not found'}), 404
    teacher = Teacher.query.filter_by(id=session.teacher_id).first()
    book = Book.query.filter_by(id=session.book_id).first()
    session_info = {
        'id': session.id,
        'name': session.name,
        'img': session.img,
        'capacity': session.capacity,
        'book_id': session.book_id,
        'teacher_id': session.teacher_id,
        'location': session.location.value,
        'start_date': str(session.start_date),
        'end_date': str(session.end_date),
        'pack_id': session.pack_id,
        'description': session.description,
        'active': session.active,
        'book_name' : book.title,
        'teacher_name' : teacher.username,
        'meet_link':session.meet_link
    }

    return jsonify({'session': session_info}), 200

@admin.route('/update_session', methods=['POST'])
# @login_required
# @admin_required
def update_session():
    try:
        data = request.json
        
        token = data['id']
        
        session_to_update = Session.query.filter_by(id=token).first()
        
        if not session_to_update:
            return jsonify({'message': 'Session not found'}), 404
        
        teacher = Teacher.query.filter_by(id=session_to_update.teacher_id).first()
        book = Book.query.filter_by(id=session_to_update.book_id).first()
        
        if 'name' in data:
            new_name = data['name']
            # Check if the new name is an empty string or if it's already in use by another session
            if not new_name.strip():
                return jsonify({'message': 'Name cannot be empty'}), 400
            elif Session.query.filter(Session.name == new_name, Session.id != token).first():
                return jsonify({'message': 'Name is already in use by another session'}), 400
            session_to_update.name = new_name
        
        session_to_update.book_id = data['book_id'] if 'book_id' in data else session_to_update.book_id
        session_to_update.teacher_id = data['teacher_id'] if 'teacher_id' in data else session_to_update.teacher_id
        session_to_update.location = data['location'] if 'location' in data else session_to_update.location
        session_to_update.start_date = data['start_date'] if 'start_date' in data else session_to_update.start_date
        session_to_update.end_date = data['end_date'] if 'end_date' in data else session_to_update.end_date
        session_to_update.description = data['description'] if 'description' in data else session_to_update.description
        session_to_update.active = data['active'] if 'active' in data else session_to_update.active
        session_to_update.capacity = data['capacity'] if 'capacity' in data else session_to_update.capacity
        session_to_update.pack_id = data['pack_id'] if 'pack_id' in data else session_to_update.pack_id
        session_to_update.meet_link = data['meet_link'] if 'meet_link' in data else session_to_update.meet_link
  
        db.session.commit()

        session_info = {
            'id': session_to_update.id,
            'name': session_to_update.name,
            'capacity': session_to_update.capacity,
            'book_id': session_to_update.book_id,
            'teacher_id': session_to_update.teacher_id,
            'location': session_to_update.location.value,
            'start_date': str(session_to_update.start_date),
            'end_date': str(session_to_update.end_date),
            'pack_id': session_to_update.pack_id,
            'description': session_to_update.description,
            'active': session_to_update.active,
            'book_name': book.title,
            'teacher_name': teacher.username,
            'meet_link':session_to_update.meet_link
        }
        
        return jsonify({'message': 'Session details updated successfully', 'session': session_info}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    

## @brief Route for suggesting books for a user based on their preferences.
#
# This route is used by administrators to suggest books to a user based on their preferences and previous follows.
# The function accepts a POST request with JSON data containing the user's email.
# The function calculates the user's most followed book category and suggests books from that category.
# If there are suggestions available, a JSON object containing the book details is returned as a response.
# If no suggestions are found, a JSON object with a message indicating so is returned.
#
# @param email: Email of the user for whom the book suggestions are to be made.
#
# @return: A JSON object containing book suggestions or a message if no suggestions are found.
@admin.route('/suggest_book_for_user', methods=['POST'])
@login_required
@admin_required
def suggest_book_for_user():
    try:
        email = request.json['email']

        most_category = db.session.query(Book.category, func.count().label('count')).filter(User.email == email).join(Follow_session, Follow_session.user_id == User.id).join(Session, Session.id == Follow_session.session_id).join(Book,Book.id==Session.book_id).group_by(Book.category).order_by(func.count().desc()).first()

        if most_category:
            category, _ = most_category  # Extract the category from the tuple
            
            books = Book.query.filter(Book.category == category).all()
            suggestions = []
            for book in books:
                suggestions.append({
                    'title': book.title,
                    'author': book.author,
                    'page_number': book.page_number,
                    'release_date': book.release_date,
                    'category': book.category
                })

            return jsonify({'suggestions': suggestions}), 200
        else:
            return jsonify({'message': 'No suggestion found'}), 404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/show_all_books', methods=['GET'])
def get_all_books():
    try:
        # Query all books from the database
        books = Book.query.all()
   
        # Create a list to store the book data
        book_list = []

        # Loop through the books and create a dictionary for each book
        for book in books:
            book_data = {
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'img': book.img,
                'release_date': book.release_date.strftime('%Y-%m-%d') if book.release_date else None,  
                'page_number': book.page_number,
                'category': book.category,
                'neo4j_id': book.neo4j_id,
                'desc': book.desc,
              
            }
            book_list.append(book_data)

        return jsonify(book_list), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


#get all units 
@admin.route('/show_all_units/<int:id>', methods=['GET'])
def get_all_units(id):
    try:
        # Query all books from the database
        units = Unit.query.filter_by(book_id=id).all() 
        # Create a list to store the book data
        unit_list = []
        # Loop through the books and create a dictionary for each book
        for unit in units:
            unit_data = {
                'id': unit.id,
                'name': unit.name,
                'book_id': unit.book_id  
            }
            unit_list.append(unit_data)
        return jsonify(unit_list), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
#delete unit 
@admin.route('/delete_unit', methods=['POST'])
# @login_required
# @admin_required
def delete_unit():
    try:
        token = request.json['id']
        unit = Unit.query.filter_by(id=token).first()
        if not unit:
            return jsonify({'message': 'Unit not found'}), 404
        else:
            db.session.delete(unit)  # Corrected from 'unit' to 'unit'
            db.session.commit()
            return jsonify({'message': 'Unit is successfully deleted'}), 200
    except Exception as e:
        return jsonify({'message': f'Internal server error: {str(e)}'}), 500

#create unit 
@admin.route('/create_unit',methods=['POST'])
# @login_required
# @admin_required
def create_unit():
    try:
        data = request.get_json()
        name=data['name']
        book_id=data['book_id']
        exist_unit=Unit.query.filter_by(name=name,book_id=book_id).first()
 
        if exist_unit :
            return jsonify({'message':'Name already exist'}),404
        else:

           unit=Unit(name=name,book_id=book_id)  
           if unit:
            db.session.add(unit)
            db.session.commit()
            unit_data = {
            'id': unit.id,
            'name': unit.name,
            'book_id': unit.book_id,

        }
            return jsonify({'message':'Unit is sucessfully created','unit':unit_data}),201
           else:
            return jsonify({'message':'Somthing wrong please try later'}),404
    except Exception as e:
        logging.error(f" {str(e)} is required")
        return jsonify({'message':f" {str(e)} is required"}),500
    
#update unit 
@admin.route('/update_unit', methods=['PUT'])
def update_unit():
    try:
        data = request.get_json()

        if 'id' not in data:
            return jsonify({'message': 'Unit ID is missing in the request body'}), 400

        unit_id = data['id']
        unit = Unit.query.get(unit_id)

        if unit is None:
            return jsonify({'message': 'Unit not found'}), 404

        if 'name' in data:
            new_name = data['name']

            # Check if the new name is an empty string or if it's already in use by another unit
            if not new_name.strip():
                return jsonify({'message': 'Name cannot be empty'}), 400
            elif Unit.query.filter(Unit.name == new_name, Unit.id != unit_id).first():
                return jsonify({'message': 'Name is already in use by another unit'}), 400

            unit.name = new_name

        db.session.commit()

        unit_data = {
            'id': unit.id,
            'name': unit.name,
            'book_id': unit.book_id,
        }

        return jsonify({'message': 'Unit updated successfully', 'unit': unit_data}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



# @admin.route('/get_book/<int:id>', methods=['GET'])
# def get_book(id):
#     try:
#         book = Book.query.get(id)

#         if book is None:
#             return jsonify({'message': 'Book not found'}), 404

#         book_data = {
#             'id': book.id,
#             'title': book.title,
#             'author': book.author,
#             'img': book.img,
#             'release_date': book.release_date.strftime('%Y-%m-%d'),  # Format the date as a string
#             'page_number': book.page_number,
#             'category': book.category,
#             'neo4j_id': book.neo4j_id,
#             'desc': book.desc,
           
#         }

#         return jsonify(book_data), 200

#     except Exception as e:
#         logging.error(f"An error occurred: {str(e)}")
#         return jsonify({'message': 'Internal server error'}), 500

## @brief Route for deleting a book from the database.
#
# This route is used by administrators to delete a book from the database based on the title and author provided.
# The function accepts a POST request with JSON data containing the title and author of the book to be deleted.
# The function retrieves the book's instance from the database and deletes it.
# If the book with the specified title and author is found and successfully deleted, a JSON object with a success message is returned.
# If no book with the specified title and author is found, a JSON object with a message indicating so is returned.
#
# @param title: Title of the book to be deleted.
# @param author: Author of the book to be deleted.
#
# @return: A JSON object indicating whether the book deletion was successful or not.

@admin.route('/delete_book', methods=['POST'])
# @login_required
# @admin_required
def delete_book():
    try:
        token = request.json['id']
        book = Book.query.filter_by(id=token).first()
        if not book:
            return jsonify({'message': 'Book not found'}), 404
        else:
            session=Session.query.filter_by(book_id=book.id).first()
            book_pack=Book_pack.query.filter_by(book_id=book.id).first()
            
            db.session.delete(book_pack) if book_pack else None
            db.session.delete(session) if session else None
            db.session.commit()
                
            db.session.delete(book)
            db.session.commit()
            return jsonify({'message': 'Book is successfully deleted'}), 200
    except:
        return jsonify({'message': 'Internal server error'}), 500


## @brief Route for creating a new book in the database.
#
# This route is used by administrators to create a new book in the database with the provided information.
# The function accepts a POST request with JSON data containing the book's title, author, release date, page number, and category.
# A new instance of the Book model is created with the provided data and added to the database.
# If the book creation is successful, a JSON object with a success message is returned.
#
# @param title: Title of the new book.
# @param author: Author of the new book.
# @param release_date: Release date of the new book in the format 'YYYY-MM-DD'.
# @param page_number: Number of pages in the new book.
# @param category: Category of the new book.
#
# @return: A JSON object indicating whether the book creation was successful or not.
@admin.route('/create_book',methods=['POST'])
# @login_required
# @admin_required
def create_book():   
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['title']
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400

        title=request.json['title']
        author=request.json['author']
        img = request.json['img']
        release_date=request.json['release_date']
        page_number=request.json['page_number']
        category=request.json['category']
        neo4j_id=request.json['neo4j_id']
        desc =request.json['desc']
       
        

      


        exist_book=Book.query.filter_by(title=title).first()
        
        if exist_book :
            return jsonify({'message':'Book already exist'}),404
        else:

           book=Book(title=title,author=author,img=img,release_date=release_date,page_number=page_number,category=category,neo4j_id=neo4j_id,desc=desc)  
           if  book:
            db.session.add(book)
            db.session.commit()
            book_data = {
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'img': book.img,
            'release_date':  str(book.release_date),  # Format the date as a string
            'page_number': book.page_number,
            'category': book.category,
            'neo4j_id': book.neo4j_id,
            'desc': book.desc,
        }
            return jsonify({'message':'Book is sucessfully created','book':book_data}),200
           else:
            return jsonify({'message':'Somthing wrong please try later'}),404
    except Exception as e:
        logging.error(f" {str(e)} is required")
        return jsonify({'message':f" {str(e)} is required"}),500
    

@admin.route('/update_book', methods=['PUT'])
def update_book():
    try:
        data = request.get_json()

        if 'id' not in data:
            return jsonify({'message': 'Book ID is missing in the request body'}), 400

        book_id = data['id']
        book = Book.query.get(book_id)

        if book is None:
            return jsonify({'message': 'Book not found'}), 404

        if 'title' in data:
            new_title = data['title']

            # Check if the new title is an empty string or if it's already in use by another book
            if not new_title.strip():
                return jsonify({'message': 'Title cannot be empty'}), 400
            elif Book.query.filter(Book.title == new_title, Book.id != book_id).first():
                return jsonify({'message': 'Title is already in use by another book'}), 400

            book.title = new_title

        if 'author' in data:
            book.author = data['author']
        if 'img' in data:
            book.img = data['img']
        if 'release_date' in data:
            book.release_date = data['release_date']
        if 'page_number' in data:
            book.page_number = data['page_number']
        if 'category' in data:
            book.category = data['category']
        if 'desc' in data:
            book.desc = data['desc']
        if 'neo4j_id' in data:
            book.neo4j_id = data['neo4j_id']

        db.session.commit()

        book_data = {
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'img': book.img,
            'release_date': book.release_date.strftime('%Y-%m-%d'),  # Format the date as a string
            'page_number': book.page_number,
            'category': book.category,
            'neo4j_id': book.neo4j_id,
            'desc': book.desc,
            'shcool_id':book.shcool_id
        }

        return jsonify({'message': 'Book updated successfully', 'book': book_data}), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_book/<int:id>', methods=['GET'])
def get_book(id):
    try:
      
        book = Book.query.get(id)
        if book is None:
            return jsonify({'message': 'Book not found'}), 404
        book_data = {
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'img': book.img,
            'release_date': book.release_date.strftime('%Y-%m-%d'), 
            'page_number': book.page_number,
            'category': book.category,
            'neo4j_id': book.neo4j_id,
            'desc': book.desc,
            # 'shcool_id': book.shcool_id,
        }

        return jsonify(book_data), 200

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/create_pack', methods=['POST'])
def create_pack():
    try:
        data = request.get_json()
        # Validate required fields
        required_fields = ['title', 'level',]
        for field in required_fields:
            if field not in data or not data[field].strip():
                return jsonify({'message': f'{field.capitalize()} is required'}), 400
        duration= data['duration']
        title = data['title']
        level = data['level']
        img = data['img']
        age = data.get('age')
        price = data['price']
        discount = data['discount']
        desc = data['desc']
        faq = data['faq']
        shcool_id =request.json['school_id']
        public=data['public']
        # Check if the title is already used
        if Pack.query.filter_by(title=title).first():
            return jsonify({'message': 'Title is already used'}), 409
            
        invoicing_product ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}',
                'title': title,
                'price': price,
                'vat':0,
                'quantity': 999,
                }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/product/create', json=invoicing_product)  
        if invoicing_response.status_code==201:
            invoicing_data = invoicing_response.json()
            
            prodcut_id = invoicing_data['_id']
            # Create a new pack
            pack = Pack(title=title, level=level, img=img, age=age, price=price, discount=discount, desc=desc,faq=faq,duration=duration,product_id_invoicing_api=prodcut_id,shcool_id=shcool_id)
            db.session.add(pack)
            db.session.commit()
            pack_data = {
               'id': pack.id,
               'title': pack.title,
               'level': pack.level,
               'img': pack.img,
               'age': pack.age.value,
               'price': pack.price,
               'discount': pack.discount,
               'desc': pack.desc,
               'book_number': pack.book_number,
               'faq' : pack.faq,
               'duration':pack.duration,
               'product_id_invoicing_api':prodcut_id,
               'shcool_id' :pack.shcool_id,
               'public':pack.public
                }
            return jsonify({'message': 'Pack is successfully created', 'pack': pack_data}), 201
    except Exception as e:
        print(e)  # Log the error for debugging
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/add_book_to_pack',methods=['POST'])
# @login_required
# @admin_required
def add_book_to_pack():
    try:
        pack_token=request.json['pack_id']
        book_token=request.json['book_id']
        
        book=Book.query.filter_by(id=book_token).first()
        pack=Pack.query.filter_by(id=pack_token).first()
        
        if book and pack:
            existing_book=Book_pack.query.filter_by(book_id=book.id,pack_id=pack.id).first()
            if not existing_book:
                    book_pack=Book_pack(pack_id=pack.id,book_id=book.id)
                    pack.book_number+=1
                    db.session.add(book_pack)
                    db.session.add(pack)
                    db.session.commit()
                    book_data = {
                        'id': book.id,
                        'title': book.title,
                        'author': book.author,
                        'img': book.img,
                        'release_date': book.release_date.strftime('%Y-%m-%d'),  # Format the date as a string
                        'page_number': book.page_number,
                        'category': book.category,
                        'neo4j_id': book.neo4j_id
        }



                    return jsonify({'message':'Book is sucessfully added','book':book_data}), 200
            else:
                return jsonify({'message':'Book already exist in this pack'}),400
        else:
            return jsonify({'message':'Book not found or pack not found'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500


@admin.route('/delete_book_from_pack', methods=['POST'])
# @login_required
# @admin_required
def delete_book_from_pack():
    try:
        book_token = request.json['book_id']
        pack_token=request.json['pack_id']
        
        pack=Pack.query.filter_by(id=pack_token).first()
        
        book = Book.query.filter_by(id=book_token).first()
        
        if book:
            if not pack:
                return jsonify({'message': 'Pack not found'}), 404
            else:
                record = Book_pack.query.filter_by(book_id=book.id,pack_id=pack.id).first()
                if record:
                    pack.book_number-=1
                    db.session.delete(record)
                    db.session.commit()
                    
                    return jsonify({'message': 'Book removed from pack successfully'}), 200
                else:
                    return jsonify({'message': 'Book is not in this pack'}), 404
        else:
            return jsonify({'message': 'Book not found'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500


@admin.route('/delete_pack', methods=['POST'])
# @login_required
# @admin_required
def delete_pack():
    try:
        token=request.json['id']
        pack=Pack.query.filter_by(id=token).first()
        if pack:
            book_packs=Book_pack.query.filter_by(pack_id=pack.id).all()
            code_packs=Code.query.filter_by(pack_id=pack.id).all()
            follow_packs=Follow_pack.query.filter_by(pack_id=pack.id).all()
            sessions=Session.query.filter_by(pack_id=pack.id).all()


            [db.session.delete(book_pack) for book_pack in book_packs if book_pack]
            [db.session.delete(code_pack) for code_pack in code_packs if code_pack]
            [db.session.delete(follow_pack) for follow_pack in follow_packs if follow_pack]
            [db.session.delete(session) for session in sessions if session]
            db.session.commit()

            db.session.delete(pack)
            db.session.commit()
            return jsonify({'message':'Pack is succesfully deleled'}), 200
        else:
            return jsonify({'message':'Pack not found'}), 404
    except Exception as error:
        print(error)
        return jsonify({'message':'Internal server error'}), 500
        


@admin.route('/update_pack_details', methods=['POST'])
# @login_required
# @admin_required
def update_pack_details():
    try:
        data = request.json
        
        pack_token = data['id']
    
        pack_to_update = Pack.query.filter_by(id=pack_token).first()
        
        if not pack_to_update:
            return jsonify({'message': 'Pack not found'}), 404
        
        if 'title' in data:
            new_title = data['title']
            # Check if the new title is an empty string or if it's already in use by another pack
            if not new_title.strip():
                return jsonify({'message': 'Title cannot be empty'}), 400
            elif Pack.query.filter(Pack.title == new_title, Pack.id != pack_token).first():
                return jsonify({'message': 'Title is already in use by another pack'}), 400
            pack_to_update.title = new_title
        
        if 'level' in data:
            new_level = data['level']
            if not new_level.strip():
                return jsonify({'message': 'Level cannot be empty'}), 400
            pack_to_update.level = new_level
            
        pack_to_update.duration= data['duration'] if 'duration' in data else pack_to_update.duration
        pack_to_update.img = data['img'] if 'img' in data else pack_to_update.img
        pack_to_update.price = data['price'] if 'price' in data else pack_to_update.price
        pack_to_update.discount = data['discount'] if 'discount' in data else pack_to_update.discount
        pack_to_update.faq= data['faq'] if 'faq' in data else pack_to_update.faq
        pack_to_update.age = data['age'] if 'age' in data else pack_to_update.age.value
        pack_to_update.desc = data['desc'] if 'desc' in data else pack_to_update.desc
        pack_to_update.duration = data['duration'] if 'duration' in data else pack_to_update.duration 
        pack_to_update.public = data['public'] if 'public' in data else pack_to_update.public 

        
        db.session.commit()
        
        pack_data = {
            'id': pack_to_update.id,
            'title': pack_to_update.title,
            'level': pack_to_update.level,
            'img': pack_to_update.img,
            'age': pack_to_update.age.value,
            'price': pack_to_update.price,
            'discount': pack_to_update.discount,
            'desc': pack_to_update.desc,
            'book_number': pack_to_update.book_number,
            'faq' : pack_to_update.faq,
            'duration':pack_to_update.duration,
            'public':pack_to_update.public 
        }

        return jsonify({'message': 'Pack details updated successfully', 'pack': pack_data}), 200
    except Exception as e:
        return jsonify({'message': 'An error occurred', 'error': str(e)}), 500

    
    
@admin.route('/show_all_teacher_postulate')
@login_required
@admin_required
def show_all_teacher_postulate():
    try:
        teacher_postulates=Teacher_postulate.query.all()
        teacher_submits=[]

        for teacher_submit in teacher_postulates:
            teacher_submits.append({
            'username': User.query.filter_by(id=teacher_submit.id).first().username or None,
            'email': User.query.filter_by(id=teacher_submit.id).first().email or None,
            'description' :teacher_submit.description,
            'study_level': teacher_submit.study_level,
            'selected' : teacher_submit.selected
        })

        return jsonify({'teacher_submits':teacher_submits}),200
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/accept_teacher_job',methods=['POST'])
@login_required
@admin_required
def accept_teacher_job():
    try:
        email=request.json['email']
        reader =Reader.query.filter_by(email=email).first()
        if reader:
            teacher_postulate=Teacher_postulate.query.filter_by(id=reader.id).first()
            if teacher_postulate:
                db.session.delete(teacher_postulate)
                db.session.commit()
                db.session.delete(reader)
                db.session.commit()
                new_teacher=Teacher(id=reader.id,username=reader.username,email=reader.email,password_hashed=reader.password_hashed,created_at=reader.created_at,confirmed=True,description=teacher_postulate.description,study_level=teacher_postulate.study_level)
                db.session.add(new_teacher)
                db.session.commit()

                return jsonify({'message':'Switched to teacher successfully'}),200
            else:
                return jsonify({'message':'The user hadn\'t postulate to teacher job'}),404
        else:
            return jsonify({'message':'Invalid email or already switched to teacher'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/reject_teacher_job',methods=['POST'])
@login_required
@admin_required
def reject_teacher_role():
    try:
        email=request.json['email']
        reader=Reader.query.filter_by(email=email).first()
        if reader:
            teacher_postulate=Teacher_postulate.query.filter_by(id=reader.id).first()
            if teacher_postulate:
                db.session.delete(teacher_postulate)
                db.session.commit()
                return jsonify({'message':'Teacher job rejected successfully'}),200
            else:
                return jsonify({'message':'The user hadn\'t postulate to teacher job'}),404
        else:
            return jsonify({'message':'Invalid email ,any reader matched'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500
        

@admin.route('/revoke_teacher_role',methods=['POST'])
@login_required
@admin_required
def revoke_teacher_role():
    try:
        email=request.json['email']
        teacher=Teacher.query.filter_by(email=email).first()

        if teacher:
            reader=Reader(id=teacher.id,username=teacher.username,email=teacher.email,password_hashed=teacher.password_hashed,confirmed=True,created_at=teacher.created_at)
            db.session.delete(teacher)
            db.session.commit()
            db.session.add(reader)
            db.session.commit()
            return jsonify({'message':'Teacher role\'s revoked successfully'}),200
        else:
            return jsonify({'message':'Invalid email'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/show_pack_follow_requests')
# @login_required
# @admin_required
def show_pack_follow_requests():
    try:
        school_id = User_shcool.query.filter_by(user_id=current_user.id).first().shcool_id
        pack_follow_requests = Follow_pack.query.all()
        
        all_packs = []
        for follow_request in pack_follow_requests:
            pack = Pack.query.filter_by(id=follow_request.pack_id,shcool_id=school_id).first()
            user_info = User.query.filter_by(id=follow_request.user_id).first()
            if pack :
                all_packs.append({
                    'pack_id': pack.id,
                    'pack_title': pack.title,
                    'user_id': user_info.id,
                    'username': user_info.username,
                    'email': user_info.email,
                    'approved':follow_request.approved
                     })

        return jsonify({'pack_follow_requests': all_packs}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
# Define a new route to approve follow requests.
@admin.route('/approve_pack_follow_request', methods=['POST'])
# @login_required
# @admin_required
def approve_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = True
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

 # Define a new route to approve follow requests.
@admin.route('/reject_pack_follow_request', methods=['POST'])
# @login_required
# @admin_required
def reject_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = False
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500       

# Define a route to delete a follow request.
@admin.route('/delete_follow_request', methods=['POST'])
# @login_required
# @admin_required
def delete_follow_request():
    try:
        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400

        # Find the follow request by pack_id and user_id.
        follow_request = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Delete the follow request.
        db.session.delete(follow_request)
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request deleted'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

#create follow pack 
@admin.route('/create_follow_pack', methods=['POST'])
# @login_required
def create_follow_pack():
    try:
        pack_id = request.json.get('pack_id')
        user_id = request.json.get('user_id')

        if not pack_id or not user_id:
            return jsonify({'message': 'Pack ID and User ID are required'}), 400

        # Find the pack
        pack = Pack.query.filter_by(id=pack_id).first()
        if not pack:
            return jsonify({'message': 'Pack not found'}), 404

        # Check if the user already follows the pack
        existing_pack = Follow_pack.query.filter_by(user_id=user_id, pack_id=pack_id).first()
        if existing_pack:
            return jsonify({'message': 'You already follow this pack'}), 400

        # Add a new follow_pack record
        follow_pack_entry = Follow_pack(user_id=user_id, pack_id=pack_id, approved=True)
        db.session.add(follow_pack_entry)
        db.session.commit()

        followed_pack = {
            'approved': follow_pack_entry.approved,
            'id': pack.id,
            'level': pack.level,
            'book_number': pack.book_number,
            'price': pack.price,
            'title': pack.title
        }

        return jsonify({'message': 'Pack successfully added to your pack list', 'followed_pack': followed_pack}), 200

    except Exception as e:
        print(f"Error: {e}")  # Log the error for debugging
        return jsonify({'message': 'Internal server error'}), 500




# Define a route to get follow requests by user and pack ID.
@admin.route('/get_one_pack_follow_requests', methods=['POST'])
# @login_required
# @admin_required
def get_one_pack_follow_requests():
    try:


        # Get pack_id and user_id from the request JSON data.
        data = request.get_json()
        pack_id = data.get('pack_id')
        user_id = data.get('user_id')

        # Check if both pack_id and user_id are provided.
        if not pack_id or not user_id:
            return jsonify({'message': 'Both pack_id and user_id are required in the request body'}), 400

        # Find follow requests by pack_id and user_id.
        follow_requests = Follow_pack.query.filter_by(pack_id=pack_id, user_id=user_id).all()
        
        # Check if any follow requests exist.
        if not follow_requests:
            return jsonify({'message': 'No follow requests found for the specified user and pack'}), 404

        # Serialize the follow requests.
        all_requests = []
        for pack_request in follow_requests:

            pack = Pack.query.filter_by(id=pack_request.pack_id).first()
            user_info = User.query.filter_by(id=pack_request.user_id).first()
            all_requests.append({
                'pack_title': pack.title,
                'username': user_info.username,
                'email': user_info.email,
                'pack_id': pack_request.pack_id,
                'user_id': pack_request.user_id,
                'approved': pack_request.approved
            })

        return jsonify({'follow_requests': all_requests}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


#create follow session 
@admin.route('/create_follow_session', methods=['POST'])
# @login_required
def create_follow_session():
    try:
        session_id = request.json.get('session_id')
        user_id = request.json.get('user_id')

        if not session_id or not user_id:
            return jsonify({'message': 'Session ID and User ID are required'}), 400

        session = Session.query.filter_by(id=session_id).first()
        if not session:
            return jsonify({'message': 'Session not found'}), 404
        user = User.query.filter_by(id=user_id).first()
        if not user :
            return jsonify({'message': 'User not found'}), 404
            
        follow_pack = Follow_pack.query.filter_by(pack_id=session.pack_id, user_id=user_id).first()
        if not follow_pack or not follow_pack.approved:
            return jsonify({'message': 'No matching or approved Follow_pack found'}), 404

        follows_count = Follow_session.query.filter_by(session_id=session.id).count()
        if session.capacity <= follows_count:
            return jsonify({'message': 'Session is full'}), 404

        # Follow book if not already followed
        follow_book_exists = Follow_book.query.filter_by(
            user_id=user_id, book_id=session.book_id, pack_id=session.pack_id
        ).first()
        if not follow_book_exists:
            follow_book = Follow_book(user_id=user_id, book_id=session.book_id, pack_id=session.pack_id)
            db.session.add(follow_book)

        # Follow session
        follow = Follow_session(user_id=user_id, session_id=session_id, approved=True)
        db.session.add(follow)
        db.session.commit()
        

        followed_session= {
                    'session_id': session.id,
                    'session_name': session.name,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'approved':follow.approved
                     }
        return jsonify({'message': 'session has been created ','follow_session':followed_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500





@admin.route('/show_session_follow_requests')
# @login_required
# @admin_required
def show_session_follow_requests():
    try:
        school_id = User_shcool.query.filter_by(user_id=current_user.id).first().shcool_id
        session_follow_requests = Follow_session.query.all()
        
        all_session = []
        for follow_request in session_follow_requests:
            session = Session.query.filter_by(id=follow_request.session_id).first()
            pack = Pack.query.filter_by(id=session.pack_id,shcool_id=school_id).first()
            user_info = User.query.filter_by(id=follow_request.user_id).first()
            if pack :
                
                all_session.append({
                    'session_id': session.id,
                    'session_name': session.name,
                    'user_id': user_info.id,
                    'username': user_info.username,
                    'email': user_info.email,
                    'approved':follow_request.approved
                     })
        return jsonify({'session_follow_requests': all_session}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/approve_session_follow_request', methods=['POST'])
# @login_required
# @admin_required
def approve_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = True
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/reject_session_follow_request', methods=['POST'])
# @login_required
# @admin_required
def reject_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()

        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Update the 'approved' attribute to True.
        follow_request.approved = False
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request approved'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500
        
# Define a route to delete a follow request.
@admin.route('/delete_session_follow_request', methods=['POST'])
# @login_required
# @admin_required
def delete_session_follow_request():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400

        # Find the follow request by session_id and user_id.
        follow_request = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).first()
        session = Session.query.filter_by(id=session_id).first()
        book_follow = Follow_book.query.filter_by(book_id=session.book_id, user_id=user_id).first()
        
        # Check if the follow request exists.
        if follow_request is None:
            return jsonify({'message': 'Follow request not found'}), 404

        # Delete the follow request.
        if book_follow :
            db.session.delete(book_follow)
        db.session.delete(follow_request)
        db.session.commit()  # Assuming you're using SQLAlchemy and have a database session.

        return jsonify({'message': 'Follow request deleted'}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500


# Define a route to get follow requests by user and session ID.
@admin.route('/get_one_session_follow_requests', methods=['POST'])
# @login_required
# @admin_required
def get_one_session_follow_requests():
    try:
        # Get session_id and user_id from the request JSON data.
        data = request.get_json()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        # Check if both session_id and user_id are provided.
        if not session_id or not user_id:
            return jsonify({'message': 'Both session_id and user_id are required in the request body'}), 400

        # Find follow requests by session_id and user_id.
        follow_requests = Follow_session.query.filter_by(session_id=session_id, user_id=user_id).all()

        # Check if any follow requests exist.
        if not follow_requests:
            return jsonify({'message': 'No follow requests found for the specified user and session'}), 404

        # Serialize the follow requests.
        all_requests = []
        for session_request in follow_requests:
            session = Session.query.filter_by(id=session_request.session_id).first()
            user_info = User.query.filter_by(id=session_request.user_id).first()
            all_requests.append({
                'username': user_info.username,
                'email': user_info.email,
                'session_name': session.name,
                'session_id': session_request.session_id,
                'user_id': session_request.user_id,
                'approved': session_request.approved
            })

        return jsonify({'follow_requests': all_requests}), 200
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@admin.route('/add_quiz_to_session', methods=['POST'])
# @login_required
# @admin_required
def add_quiz_to_session():
    try:
        # Get data from the request
        data = request.get_json()
        session_id = data['session_id']
        quiz_token = data['quiz_token']
        release_date = data.get('release_date')  
       
        # Check if  the quiz already exists in the session
        if Session_quiz.query.filter_by(session_id=session_id, quiz_token=quiz_token).first():
            return jsonify({'message': 'This quiz is already exists in the session.'}), 409  # Conflict
        else:
            # Create a new session_quiz
            new_session_quiz = Session_quiz(
                session_id=session_id,
                quiz_token=quiz_token,
                release_date=release_date if release_date else None  
            )

            # Add the user to the database
            db.session.add(new_session_quiz)
            db.session.commit()

            # Return a success response
            response_data = {
                'message': 'Your Quiz has been successfully added.',
                'quiz_session': {
                    'session_id': session_id,
                    'quiz_token': quiz_token,
                    'release_date': new_session_quiz.release_date,
                    'id': new_session_quiz.id,
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/delete_quiz_from_session',methods=['POST'])
# @login_required
# @admin_required
def delete_quiz_from_session():
    try:
        session_id = request.json['session_id']
        quiz_token = request.json['quiz_token']

        quiz = Session_quiz.query.filter_by(session_id=session_id,quiz_token=quiz_token).first()
        
        if quiz:
            db.session.delete(quiz)
            db.session.commit()
            return jsonify({'message': 'Quiz deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid Quiz'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_quiz_in_session',methods=['POST'])
# @login_required
# @admin_required
def get_quiz_in_session():
    try:
        session_id = request.json['session_id']
        

        quizs = Session_quiz.query.filter_by(session_id=session_id).all()
        quiz_data=[]
        for quiz in quizs :
            quiz_data.append({
                'session_id': quiz.session_id,
                'quiz_token': quiz.quiz_token,
                'release_date': quiz.release_date,
                'id': quiz.id,
            })
        return jsonify({
            'quizes': quiz_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500




# Get route to retrieve pack and its associated codes
@admin.route('/code_in_pack/<int:pack_id>', methods=['GET'])
def get_pack(pack_id):
    pack = Pack.query.get(pack_id)
    if pack is not None:
        # Retrieve associated codes for the pack
        codes = Code.query.filter_by(pack_id=pack_id,status=StatusEnum.ACTIVE).all()
        pack_data = {
            "id": pack.id,
            "title": pack.title,
            "codes": [{"code": code.code, "status": code.status.value,'id':code.id,'pack_id':code.pack_id} for code in codes]
        }
        return jsonify(pack_data)
    else:
        return jsonify({"error": "Pack not found"}), 404
@admin.route('/delete_code/<int:code_id>', methods=['DELETE'])
def delete_code(code_id):
    code = Code.query.get(code_id)

    if code is not None:
        db.session.delete(code)
        db.session.commit()
        return jsonify({"message": "Code deleted successfully"})
    else:
        return jsonify({"error": "Code not found"}), 404

def generate_unique_code(pack_id):
   
    characters = string.ascii_letters + string.digits  

  
    code_length = 8
    generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

  
    while Code.query.filter_by(pack_id=pack_id, code=generated_code).first() is not None:
    
        generated_code = ''.join(secrets.choice(characters) for _ in range(code_length))

    return generated_code





@admin.route('/generate_code_in_pack/<int:pack_id>', methods=['POST'])
def generate_codes(pack_id):
    pack = Pack.query.get(pack_id)
    if pack is not None:
        data = request.get_json()
        num_codes_to_generate = data.get('num_codes', 10) 
        generated_codes = []

        for _ in range(num_codes_to_generate):
       
            code = generate_unique_code(pack_id)
            
            new_code = Code(pack_id=pack_id, code=code)
            db.session.add(new_code)
            generated_codes.append(code)

        db.session.commit()
        return jsonify({"message": f"{num_codes_to_generate} codes generated successfully", "generated_codes": generated_codes})
    else:
        return jsonify({"error": "Pack not found"}), 404

@admin.route('update_code/<int:code_id>', methods=['PUT'])
def update_code_status(code_id):
    code = Code.query.get(code_id)
    if code is not None:
        data = request.get_json()
        new_status = data.get('status')
        
        # Check if the provided status is valid
        if new_status in [status.value for status in StatusEnum]:
            code.status = StatusEnum(new_status)
            db.session.commit()
            return jsonify({"message": f"Code status updated to {new_status}"})
        else:
            return jsonify({"error": "Invalid status provided"}), 400
    else:
        return jsonify({"error": "Code not found"}), 404

@admin.route('/get_code/<string:code_client>', methods=['GET'])
def get_code(code_client):
    try:
        print(code_client)
        code = Code.query.filter_by(code=code_client).first()

        if code:  
            code_data = {
                "id": code.id,
                "code": code.code,
                "user_id": code.user_id,
                "pack_id": code.pack_id,
                "status":code.status.value
            }
            return jsonify({"code": code_data})
        else:
            return jsonify({"error": "Code not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin.route('/get_all_logs', methods=['GET'])
def get_all_logs():
   
    try:
        # Query the UserLog table to get all logs
        user_logs = UserLog.query.all()

        # Create a list to store log data
        logs = []

        # Iterate through user logs
        for log in user_logs:
            log_data = {
                'id': log.id,
                'user_agent': log.user_agent,
                'user_ip': log.user_ip,
                'referer': log.referer,
                'user_country': log.user_country,
                'user_city': log.user_city,
                'user_id':log.user_id,
                'visit_duration':log.visit_duration,
                'browser':log.browser,
                'system':log.system
            }

            # Check if user_id is not None in the UserLog
            if log.user_id:
                user = User.query.get(log.user_id)
                if user:
                    log_data['user_email'] = user.email

            logs.append(log_data)

        return jsonify({'logs': logs}), 200
    except Exception as error:
        return jsonify({'message': 'Error retrieving logs', 'error': str(error)}), 500

@admin.route('/get_dashboard_analytics', methods=['GET'])
def get_dashboard_admin():
    try:
        user_logs = UserLog.query.all()
        users = User.query.all()
        user_counts = [0] * 12
        log_counts = [0] * 12
        visit_duration_count = [0] * 12
        total_visit_duration = 0
        browser_counts = {}
        country_counts ={}
        system_counts ={}

        for user in users:
            month = user.created_at.month
            user_counts[month - 1] += 1
        for log in user_logs:
            month = log.created_at.month
            log_counts[month - 1] += 1
            total_visit_duration += log.visit_duration
            visit_duration_count[month - 1] += round(log.visit_duration / 60)

            # Update browser counts
            if log.browser in browser_counts:
                browser_counts[log.browser] += 1
            else:
                browser_counts[log.browser] = 1
            if log.user_country in country_counts :
                country_counts[log.user_country]+=1  
            else :
                  country_counts[log.user_country]=1 
            if log.system in system_counts :
                system_counts[log.system]+=1  
            else :
                  system_counts[log.system]=1



        total_users = sum(user_counts)
        total_logs = sum(log_counts)
        total_duration = sum(visit_duration_count) *60
        average_visit_duration =( total_visit_duration / total_logs ) if total_logs > 0 else 0

        # Calculate browser percentages
        total_browser_logs = sum(browser_counts.values())
        browser_percentages = [{'browser': browser, 'percent': round(count / total_browser_logs * 100),'users':count} for browser, count in
                               browser_counts.items()]
        

        # Calculate country percentages
        total_country_logs = sum(country_counts.values())
        country_percentages = [{'country': country, 'percent': round(count / total_country_logs * 100),'users':count} for country, count in
                               country_counts.items()]   

        # Calculate system percentages
        total_system_logs = sum(system_counts.values())
        system_percentages = [{'system': system, 'percent': round(count / total_system_logs * 100),'users':count} for system, count in
                               system_counts.items()]   
        


       
        result = {
            'users': user_counts,
            'vistors': log_counts,
            "userCount": total_users,
            "vistorCount": total_logs,
            'averageVisitDuration': average_visit_duration ,
            "totalVisitDuration": total_duration,
            "duration": visit_duration_count,
            "browsers": browser_percentages,
            "users_by_country":country_percentages,
            "operating_system" :system_percentages

        }

        return jsonify(result)

    except Exception as error:
        return jsonify({'message': 'Error retrieving logs', 'error': str(error)}), 500  


@admin.route('/create_about_book/<int:book_id>', methods=['POST'])
def create_about_book_from_json_file(book_id):
    # Check if a record with the same book_id already exists
    existing_book = Book.query.filter_by(id=book_id).first()

    if not existing_book:
        return jsonify({'message': "Book doesn't exists"}), 400


    existing_about_book = About_Book.query.filter_by(book_id=book_id).first()
    
    if existing_about_book:
        return jsonify({'message': 'About_Book for this book already exists'}), 400
    
    if 'jsonFile' in request.files:
        json_file = request.files['jsonFile']
        try:
            # Parse the JSON data from the file
            data = json_file.read()
            about_data = json.loads(data)

            # Create a new About_Book instance
            about_book = About_Book(book_id=book_id, about=about_data)

            # Add it to the database
            db.session.add(about_book)
            db.session.commit()

            return jsonify({'message': 'About_Book created successfully','about':about_data}), 201
        except json.JSONDecodeError as e:
            return jsonify({'message': 'Invalid JSON data in the file', 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'message': 'Error creating About_Book', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'No JSON file uploaded'}), 400


@admin.route('/update_about_book/<int:book_id>', methods=['PUT', 'PATCH'])
def update_about_book_from_json(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        # Ensure the uploaded file is a JSON file
        if 'jsonFile' in request.files:
            json_file = request.files['jsonFile']
            try:
                # Parse the JSON data from the file
                data = json_file.read()
                about_data = json.loads(data)

                # Update the "about" field of the About_Book instance
                about_book.about = about_data
                
                # Commit the changes to the database
                db.session.commit()
                
                return jsonify({'message': 'About_Book updated successfully','about':about_data}), 200
            except json.JSONDecodeError as e:
                return jsonify({'message': 'Invalid JSON data in the file', 'error': str(e)}), 400
            except Exception as e:
                return jsonify({'message': 'Error updating About_Book', 'error': str(e)}), 500
        else:
            return jsonify({'message': 'No JSON file uploaded'}), 400
    else:
        return jsonify({'message': 'About_Book not found'}), 404
@admin.route('/delete_about_book/<int:book_id>', methods=['DELETE'])
def delete_about_book(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        try:
            # Delete the About_Book instance
            db.session.delete(about_book)
            db.session.commit()

            return jsonify({'message': 'About_Book deleted successfully'}), 200
        except Exception as e:
            return jsonify({'message': 'Error deleting About_Book', 'error': str(e)}), 500
    else:
        return jsonify({'message': 'About_Book not found'}), 404

@admin.route('/get_about_book/<int:book_id>')
def get_about_book_by_book_id(book_id):
    about_book = About_Book.query.filter_by(book_id=book_id).first()

    if about_book:
        # Serialize the About_Book object to a JSON response
        about_book_data = {
            'id': about_book.id,
            'book_id': about_book.book_id,
            'about': about_book.about
        }
        return jsonify(about_book_data), 200
    else:
        return jsonify({'message': 'About_Book not found for the specified book_id'}), 404 



@admin.route('/create_notification', methods=['POST'])
# @login_required
# @admin_required
def create_notification():
    try:
        # Get data from the request
        data = request.get_json()
        user_id = data['user_id']
        notification_id = data['notification_id']
     
        if Notification_user.query.filter_by(user_id=user_id, notification_id=notification_id).first():
            return jsonify({'message': 'This notification is already send it to user'}), 409  # Conflict
        else:
            new_notification = Notification_user(
                user_id=user_id,
                notification_id=notification_id,
            )

            db.session.add(new_notification)
            db.session.commit()

            # Return a success response
            response_data = {
                'message': 'Your notification has been successfully added.',
                'notification': {
                    'user_id': user_id,
                    'notification_id': notification_id,
                    'id': new_notification.id,
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        print(e)
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/delete_notification',methods=['POST'])
# @login_required
# @admin_required
def delete_notification():
    try:
        id = request.json['id']
        notification = Notification_user.query.filter_by(notification_id=id).first()
        if notification:
            db.session.delete(notification)
            db.session.commit()
            return jsonify({'message': 'Notification deleted successfully'}), 200
        else:
            return jsonify({'message': 'Invalid Notification'}), 404
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500



@admin.route('/get_notification',methods=['POST'])
# @login_required
# @admin_required
def get_notification():
    try:
        user_id = request.json['user_id']
        

        notifications = Notification_user.query.filter_by(user_id=user_id).all()
        notification_data=[]
        for notification in notifications :
            notification_data.append({
                'user_id': notification.user_id,
                'notification_id': notification.notification_id,
                'id': notification.id,
            })
        return jsonify({
            'notifications': notification_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   


@admin.route('/get_users_in_pack',methods=['POST'])
# @login_required
# @admin_required
def get_users_in_pack():
    try:
        pack_id = request.json['pack_id']
        
        users = Follow_pack.query.filter_by(pack_id=pack_id).all()
        user_data=[]
        for user in users :
            reader= User.query.filter_by(id=user.user_id).first()
            user_data.append({
                'id': user.user_id,
                'username':reader.username,
                'email':reader.email
            })
        return jsonify({
            'users': user_data
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   

@admin.route('/paser_story',methods=['POST'])
# @login_required
# @admin_required
def paser_story():
    try:
        text = request.json['text']

        print(text)
        words= get_tenses_words(text)
        
        return jsonify({
            "words":words
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500   

            
@admin.route('/get_word',methods=['POST'])
# @login_required
# @admin_required
def get_word():
    try:
        word = request.json['word']
        driver =Neo4jDriver().get_driver()
        result = DataSetDB.get_word_from_db(driver,word)

        if result.get('code') is not None and  result['code']  == 400:
            return jsonify({'message': result['message']}), 404  
     
        return jsonify({
            "res":result
        }), 200
    except Exception as e:
        # Log the error
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'message': 'Internal server error','e':{str(e)}}), 500  

#link pack to invoice 

@admin.route('/link_pack_to_invoicing')
def link_pack_to_invoicing():
    try:
        pack_id = request.json['pack_id']
        pack=Pack.query.filter_by(id=pack_id).first()
        invoicing_product ={
                'appId':f'{ConfigClass.INVOICING_API_KEY}',
                'title': pack.title,
                'price': pack.price,
                'vat':0,
                'quantity': 999,
                }
        invoicing_response = requests.post(f'{ConfigClass.INVOICING_API}/product/create', json=invoicing_product)  
        if invoicing_response.status_code==201:
            invoicing_data = invoicing_response.json()
            prodcut_id = invoicing_data['_id']
            pack.product_id_invoicing_api =prodcut_id
            db.session.commit()

            return jsonify({'message':'pack has been linked to invoicing_api'})


    except Exception as error:
        print(error)
        return jsonify({'message': 'Internal server error', 'error': str(error)}), 500


# Create
@admin.route('/create_shcool', methods=['POST'])
def create_shcool():
    try:
        data = request.get_json()
        name = data.get('name')
        if not name:
            raise ValueError('Name is required')
        new_shcool = Shcool(name=name)
        db.session.add(new_shcool)
        db.session.commit()
        result = {
            'id':new_shcool.id,
            'name':new_shcool.name
        }
        return jsonify({'message': 'Shcool created successfully','shcool':result }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Read
@admin.route('/get_all_shcools', methods=['GET'])
def get_all_shcools():
    try:
        shcools = Shcool.query.all()
        result = [{'id': shcool.id, 'name': shcool.name} for shcool in shcools]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Update
@admin.route('/update_shcool/<int:id>', methods=['PUT'])
def update_shcool(id):
    try:
        shcool = Shcool.query.get_or_404(id)
        data = request.get_json()
        name = data.get('name')
        if not name:
            raise ValueError('Name is required')
        shcool.name = name
        db.session.commit()
        res ={
            'id':id,
            'name':name
        }
        return jsonify({'message': 'Shcool updated successfully','shcool':res})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Delete
@admin.route('/delete_shcool/<int:id>', methods=['DELETE'])
def delete_shcool(id):
    try:
        shcool = Shcool.query.get_or_404(id)
        db.session.delete(shcool)
        db.session.commit()
        return jsonify({'message': 'Shcool deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin.route('/get_one_shcool/<int:id>')
def get_one_shcool(id):
    try:
        shcool = Shcool.query.get_or_404(id)
        result = {'id': shcool.id, 'name': shcool.name}
        return jsonify({'shcool': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/generate_template/<int:id>')
def generate_template(id):
    try:
        pack = Pack.query.get_or_404(id)
        book_packs = Book_pack.query.filter_by(pack_id=id).all()  
        book_pack_data = [book_pack.book_id for book_pack in book_packs]
        new_template =  Pack_template(title=pack.title,level=pack.level,desc = pack.desc,age=pack.age.value,img=pack.img,faq=pack.faq,book_pack_ids=book_pack_data)
        db.session.add(new_template)
        db.session.commit()
        return jsonify({'message': 'Template generated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/import_template/<int:id>')
def import_template(id):
    try:
       
        pack_template = Pack_template.query.get_or_404(id)      
        shcool_user = User_shcool.query.filter_by(user_id=current_user.id).first()

        book_packs_data = pack_template.book_pack_ids

        new_pack =  Pack(title=pack_template.title,level=pack_template.level,desc = pack_template.desc,age=pack_template.age,img=pack_template.img,faq=pack_template.faq,shcool_id=shcool_user.shcool_id)
        db.session.add(new_pack)       
        db.session.commit()
        
        for item in book_packs_data:
            book_pack = Book_pack(pack_id=new_pack.id, book_id=item)
            db.session.add(book_pack)
            db.session.commit()

        return jsonify({'message': 'Template imported successfully'}) 

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin.route('/pack_templates/<int:template_id>', methods=['GET'])
def get_pack_template(template_id):
    try:
        # Query the database for the Pack_template object with the given ID
        template = Pack_template.query.get(template_id)
        
        # Check if the template exists
        if template is None:
            # Return a 404 Not Found response if the template does not exist
            return jsonify({'error': 'Template not found'}), 404
        book_packs = []
        for book_pack_id in template.book_pack_ids:

            book = Book.query.get(book_pack_id)
            if book:
                book_packs.append({
                    'id': book.id,
                    'title': book.title,
                    'author': book.author,
                    'img':book.img,
                    'desc':book.desc,
                    'release_date':book.release_date,
                    'page_number':book.page_number,
                    'category':book.category
                    })

        # Serialize the Pack_template object to JSON and return it
        return jsonify({
            'id': template.id,
            'title': template.title,
            'level': template.level,
            'desc': template.desc,
            'age': template.age,
            'img': template.img,
            'faq': template.faq,
            'books': book_packs,
            'template_type': template.template_type.value ,
            'book_number':len(book_packs) 
        })
    except Exception as e:
        # Return a 500 Internal Server Error response if an unexpected error occurs
        return jsonify({'error': 'Internal Server Error', 'message': str(e)}), 500
# Define a route to handle GET requests for all Pack_template objects
@admin.route('/pack_templates', methods=['GET'])
def get_all_pack_templates():
    try:
        # Query the database to retrieve all Pack_template objects
        templates = Pack_template.query.all()

        # Serialize each Pack_template object to JSON
        serialized_templates = []
        for template in templates:
            # Retrieve each book corresponding to the book pack IDs
            book_packs = []
            for book_pack_id in template.book_pack_ids:
                book = Book.query.get(book_pack_id)
                if book:
                    book_packs.append({
                        'id': book.id,
                        'title': book.title,
                        'author': book.author,
                        'img':book.img,
                        'desc':book.desc,
                        'release_date':book.release_date,
                        'page_number':book.page_number,
                        'category':book.category
                        })

            serialized_templates.append({
                'id': template.id,
                'title': template.title,
                'level': template.level,
                'desc': template.desc,
                'age': template.age,
                'img': template.img,
                'faq': template.faq,
                'books': book_packs,
                'template_type': template.template_type.value,
                'book_number':len(book_packs)   
            })

        # Return the list of serialized Pack_template objects as JSON response
        return jsonify(serialized_templates)
    except Exception as e:
        # Return a 500 Internal Server Error response if an unexpected error occurs
        return jsonify({'error': 'Internal Server Error', 'message': str(e)}), 500  


# book Text 
@admin.route('/book_text', methods=['POST'])
def create_book_text():
    try:
        data = request.json
        print(data)
        if not data or not data.get('book_id') or not data.get('text'):
            return jsonify({"error": "Missing 'book_id' or 'text'"}), 400
     
        new_entry = Book_text(
            book_id=data['book_id'],
            text=data['text']
        )
        db.session.add(new_entry)
        db.session.commit()
        return jsonify({"message": "Book text created successfully", "id": new_entry.id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- READ ALL ---------
@admin.route('/book_text', methods=['GET'])
def get_all_book_texts():
    try:
        entries = Book_text.query.all()
        result = [{
            "id": entry.id,
            "book_id": entry.book_id,
            "text": entry.text
        } for entry in entries]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- READ ONE ---------
@admin.route('/book_text/<int:book_id>', methods=['GET'])
def get_book_text_by_book_id(book_id):
    try:
        entry = Book_text.query.filter_by(book_id=book_id).first()
        if not entry:
            return jsonify({"error": "Entry not found for the given book_id"}), 404
        return jsonify({
            "id": entry.id,
            "book_id": entry.book_id,
            "text": entry.text
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- UPDATE ---------
@admin.route('/book_text/<int:book_id>', methods=['PUT'])
def update_book_text_by_book_id(book_id):
    try:
        entry = Book_text.query.filter_by(book_id=book_id).first()
        if not entry:
            return jsonify({"error": "Entry not found for the given book_id"}), 404

        data = request.json
        if data.get('text'):
            entry.text = data['text']

        db.session.commit()
        return jsonify({"message": "Text updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------- DELETE ---------
@admin.route('/book_text/<int:id>', methods=['DELETE'])
def delete_book_text(id):
    try:
        entry = Book_text.query.get(id)
        if not entry:
            return jsonify({"error": "Entry not found"}), 404

        db.session.delete(entry)
        db.session.commit()
        return jsonify({"message": "Entry deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


##---------word defenition----------

@admin.route('/define', methods=['GET'])
def define_word():
    try:
        word = request.args.get('word')
        if not word:
            return jsonify({"error": "Please provide a word"}), 400

        definition_en = get_short_definition(word)
        definition_ar = translate_to_arabic(word)

        return jsonify({
            "word": word,
            "definition_en": definition_en,
            "definition_ar": definition_ar
        })
    
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

'''

Show all teacher postulate
Accept an Reader to be Teacher (We will a table that contain a id of the reader and incomming informations)
Deactivate a session
Read Upadate  Book
Create Read Upadate Delete Session
Create Read Upadate Delete Pack
Create Read Update Delete Reader,Teacher

'''


    