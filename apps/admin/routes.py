## @file
# Blueprint for user readers' management.
# Contains routes and functions related to reader management.

from uuid import uuid4

from flask import Blueprint,request,jsonify,abort,render_template
from flask_login import logout_user,login_required,current_user
from extensions import login_manager,mail,db
from flask_bcrypt import Bcrypt
from models.user import User,Reader,Teacher,Admin
from models.book_pack import Book_pack
from models.book import Book
from models.session import Session,Location
from models.pack import Pack
from models.follow_session import Follow_session
from models.teacher_postulate import Teacher_postulate
from models.follow_pack import Follow_pack
import logging
from apps.main.email import generate_confirmed_token
from config import ConfigClass
from flask_mail import Message
from functools import wraps
from datetime import datetime
from sqlalchemy import func
from apps.main.email import admin_confirm_token


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
def show_all_users():
    try:
        # Retrieve all readers
        readers = Reader.query.all()

        # Collect user data associated with each reader's ID
        user_data = []
        for reader in readers:
            users = User.query.filter_by(id=reader.id).all()
            for user in users:
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img':user.img,
                    'approved':user.approved
                })

        return jsonify({
            'readers': user_data
        }), 200
    except Exception as e:
        return jsonify({'message': 'Internal server error'}), 5003

# get all teachers
@admin.route('/show_all_teachers')
# @login_required
# @admin_required
def show_all_teacher():
    try:
        # Retrieve all teachers
        teachers = Teacher.query.all()

        # Collect user data associated with each teacher's ID
        user_data = []
        for teacher in teachers:
            users = User.query.filter_by(id=teacher.id).all()
            for user in users:
                user_data.append({
                    'email': user.email,
                    'username': user.username,
                    'confirmed': user.confirmed,
                    'id': user.id,
                    'img':user.img,
                    'approved':user.approved
                })

        return jsonify({
            'teachers': user_data
        }), 200
    except Exception as e:
        return jsonify({'message': 'Internal server error'}), 5003
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
                # Add other attributes as needed
            }
            return jsonify(user_data), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as error:
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
            if 'email' in data:
                user.email = data['email']
            if 'password' in data:
                if data['password'] != "":
                    user.password_hashed = bcrypt.generate_password_hash(data['password'])
                else:
                    return jsonify({'message': 'Password cannot be empty'}), 400  # Return a response for an empty password

            # Assuming you're using some sort of database session management, commit the changes
            db.session.commit()
            response_data = {
            'message': 'Teacher updated successfully',
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

        # Check if the email already exists
        if Reader.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Hash the password
            password_hash = bcrypt.generate_password_hash(password)

            # Create a new user
            new_user = Reader(
                username=username,
                email=email,
                password_hashed=password_hash,
                created_at=datetime.now(),
                confirmed=True,

               
            )

            # Add the user to the database
            db.session.add(new_user)
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
                  
                }
            }
            return jsonify(response_data), 201
    except Exception as e:
        # Handle exceptions and return an error response
        return jsonify({'message': 'Internal server error'}), 500


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

        # Check if the email already exists
        if Teacher.query.filter_by(email=email).first():
            return jsonify({'message': 'This email is already used. Please choose another'}), 409  # Conflict
        else:
            # Hash the password
            password_hash = bcrypt.generate_password_hash(password)

            # Create a new user
            new_user = Teacher(
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
            teacher.email = data['email']
        if 'password' in data:
            # Hash the new password
            teacher.password_hashed = bcrypt.generate_password_hash(data['password'])
        if 'description' in data:
            teacher.description = data['description']
        if 'study_level' in data:
            teacher.study_level = data['study_level']

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
                'study_level': teacher.study_level
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
            if user.confirmed:
                user.approved=True
                db.session.commit()
                return jsonify({'message':'Account approved sucessfully'}),200
            else:
                return jsonify({'message':'The user doesn\'t confirmed his account'}),400
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
@admin.route('/create_session',methods=['POST'])
@login_required
@admin_required
def create_session():
    try:
        book_title=request.json['title']
        author=request.json['author']
        location=request.json['location']
        session_name=request.json['name']
        price=request.json.get('price')
        discount=request.json.get('discount')
        img=request.json.get('img')
        teacher_email=request.json['teacher_email']
        date_str=request.json['date']
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d') 
        except ValueError:
            return jsonify({'message': 'Invalid date format. Use YYYY-MM-DD format.'}), 400

        if date < datetime.now():
            return jsonify({'message':'Invalid datetime'}),400 

        if not location in [location.value for location in Location]:
            return jsonify({'message':'Place must be either online or classroom'}),400

        book=Book.query.filter(Book.title==book_title,Book.author==author).first()

        if book:
            teacher=Teacher.query.filter_by(email=teacher_email).first()
            session=Session(token=str(uuid4()),book_id=book.id,teacher_id=teacher.id,location=location,name=session_name,date=date)
            db.session.add(session)
            db.session.commit()
            return jsonify({'message':'Session created successfully'}),200
        else:
            return jsonify({'message':'Book not found'}),404
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/delete_session',methods=['POST'])
@login_required
@admin_required
def delete_session():
    try:
        token=request.json['id']
        
        session=Session.query.filter_by(token=token).first()
        if session:
            follow=Follow_session.query.filter_by(session_id=session.id).first()
            db.session.delete(follow) if follow is not None else None
            db.session.commit()
            db.session.delete(session) if session is not None else None
            db.session.commit()
            return jsonify({'message':'Session is succesfully deleted'})
        else:
            return jsonify({'message':'Any session matched'})
    except:
        return jsonify({'message': 'Internal server error'}), 500


@admin.route('/update_session_details', methods=['POST'])
@login_required
@admin_required
def update_session_details():
    try:
        data = request.json
        
        token = data['id']
        
        session_to_update = Session.query.filter_by(token=token).first()
        
        if not session_to_update:
            return jsonify({'message': 'Session not found'}), 404
        
        session_to_update.name = data['new_session_name'] if 'new_session_name' in data else session_to_update.name
        session_to_update.book_id = data['book_id'] if 'book_id' in data else session_to_update.book_id
        session_to_update.teacher_id = data['teacher_id'] if 'teacher_id' in data else session_to_update.teacher_id
        session_to_update.location = data['location'] if 'location' in data else session_to_update.location
        session_to_update.date = data['date'] if 'date' in data else session_to_update.date
        
        db.session.commit()
        
        return jsonify({'message': 'Session details updated successfully'}), 200
    except Exception as e:
        return jsonify({ 'message': str(e)}), 500
    

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
@login_required
@admin_required
def delete_book():
    try:
        token = request.json['id']
        book = Book.query.filter_by(token=token).first()
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
@login_required
@admin_required
def create_book():
    try:
        title=request.json['title']
        author=request.json['author']
        img=request.json.get('img')
        release_date=request.json['release_date']
        page_number=request.json['page_number']
        category=request.json['category']
        neo4j_id=request.json['neo4j_id']

        book=Book(token=str(uuid4()),title=title,author=author,img=img,release_date=release_date,page_number=page_number,category=category,neo4j_id=neo4j_id)

        if not book:
            db.session.add(book)
            db.session.commit()
            return jsonify({'message':'Book is sucessfully created'}),200
        else:
            return jsonify({'message':'Book already exist'}),200
    except Exception as e:
        return jsonify({'message':'Internal server error'}),500
    

@admin.route('/create_pack',methods=['POST'])
@login_required
@admin_required
def create_pack():
    try:
        title=request.json['title']
        level=request.json['level']
        img=request.json['img']
        age=request.json.get('age')
        price=request.json['price']
        if Pack.query.filter_by(title=title).first():
            return jsonify({'message':'Title is already used'}), 409
        else:
            pack=Pack(token=str(uuid4()),title=title,level=level,img=img,age=age,price=price)
            db.session.add(pack)
            db.session.commit()
        return jsonify({'message':'Pack is successfully created'}), 200
    except :
        return jsonify({'message':'Internal server error'}), 500


@admin.route('/add_book_to_pack',methods=['POST'])
@login_required
@admin_required
def add_book_to_pack():
    try:
        pack_token=request.json['pack_id']
        book_token=request.json['book_id']
        
        book=Book.query.filter_by(token=book_token).first()
        pack=Pack.query.filter_by(token=pack_token).first()
        
        if book and pack:
            existing_book=Book_pack.query.filter_by(book_id=book.id,pack_id=pack.id).first()
            if not existing_book:
                    book_pack=Book_pack(pack_id=pack.id,book_id=book.id)
                    pack.book_number+=1
                    db.session.add(book_pack)
                    db.session.add(pack)
                    db.session.commit()
                    return jsonify({'message':'Book is sucessfully added'}), 200
            else:
                return jsonify({'message':'Book already exist in this pack'}),400
        else:
            return jsonify({'message':'Book not found or pack not found'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500


@admin.route('/delete_book_from_pack', methods=['POST'])
@login_required
@admin_required
def delete_book_from_pack():
    try:
        book_token = request.json['book_id']
        pack_token=request.json['pack_id']
        
        pack=Pack.query.filter_by(token=pack_token).first()
        
        book = Book.query.filter_by(token=book_token).first()
        
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
    except:
        return jsonify({'message':'Internal server error'}), 500


@admin.route('/delete_pack', methods=['POST'])
@login_required
@admin_required
def delete_pack():
    try:
        token=request.json['id']
        pack=Pack.query.filter_by(token=token).first()
        if pack:
            book_packs=Book_pack.query.filter_by(pack_id=pack.id).all()
            follow_packs=Follow_pack.query.filter_by(pack_id=pack.id).all()
            
            [db.session.delete(book_pack) for book_pack in book_packs if book_pack]
            [db.session.delete(follow_pack) for follow_pack in follow_packs if follow_pack]
            db.session.commit()

            db.session.delete(pack)
            db.session.commit()
            return jsonify({'message':'Pack is succesfully deleled'}), 200
        else:
            return jsonify({'message':'Pack not found'}), 404
    except:
        return jsonify({'message':'Internal server error'}), 500
        


@admin.route('/update_pack_details', methods=['POST'])
@login_required
@admin_required
def update_pack_details():
    try:
        data = request.json
        
        pack_token = data['id']
    
        pack_to_update = Pack.query.filter_by(token=pack_token).first()
        
        if not pack_to_update:
            return jsonify({'message': 'Pack not found'}), 404
        
        pack_to_update.title = data['new_title'] if 'new_title' in data else pack_to_update.title
        pack_to_update.level=data['level'] if 'level' in data else pack_to_update.level
        pack_to_update.img=data['img'] if 'img' in data else pack_to_update.img
        pack_to_update.price=data['price'] if 'price' in data else pack_to_update.price
        pack_to_update.discount=data['discount'] if 'discount' in data else pack_to_update.discount
        
        db.session.commit()
        
        return jsonify({'message': 'Pack details updated successfully'}), 200
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
@login_required
@admin_required
def show_pack_follow_requests():
    try:
        pack_follow_requests = Follow_pack.query.all()
        
        all_packs = []
        for follow_request in pack_follow_requests:
            pack = Pack.query.filter_by(id=follow_request.pack_id).first()
            user_info = User.query.filter_by(id=follow_request.user_id).first()

            all_packs.append({
                'pack_id': pack.id,
                'pack_title': pack.title,
                'user_id': user_info.id,
                'username': user_info.username,
                'email': user_info.email,
                'approved':follow_request.Follow_pack.approved
            })

        return jsonify({'pack_follow_requests': all_packs}), 200
    except:
        return jsonify({'message': 'Internal server error'}), 500




'''

Show all teacher postulate
Accept an Reader to be Teacher (We will a table that contain a id of the reader and incomming informations)
Deactivate a session
Read Upadate  Book
Create Read Upadate Delete Session
Create Read Upadate Delete Pack
Create Read Update Delete Reader,Teacher

'''


    