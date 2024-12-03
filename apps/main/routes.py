## @file
# Blueprint for web app content.
# Contains routes and functions related to book and session.
from flask import Blueprint,request,jsonify
from flask_login import login_required
from extensions import login_manager,db
from datetime import datetime
import logging
from models.book import Book
from models.book_pack import Book_pack
from models.session import Session
from models.user import User,Teacher
from models.follow_pack import Follow_pack
from models.pack import Pack,StatusEnum
from models.code import Code, StatusEnum as CodeStatusEnum
from flask_mail import Mail, Message
from config import ConfigClass
from flask import render_template
import os
## @brief Blueprint for the main application.
#
# This blueprint is used to define routes and views for the main application.
# The `main` blueprint is created with the provided `__name__` and will be used to register views later.
#
main=Blueprint('main',__name__,url_prefix='/main')
mail =Mail()


# Initialize the login manager for the main blueprint.
login_manager.init_app(main)


## @brief User loader function for the login manager.
#
# This function is used by the login manager to load a user from the database based on the provided `user_id`.
# The function queries the `User` model to retrieve the user with the specified `user_id` using `User.query.get(int(user_id))`.
# The loaded user will be used for authentication and authorization purposes.
#
# @param user_id: The unique identifier of the user.
# @return: The user object corresponding to the provided `user_id`.

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


## @brief Route for searching books with specific title and author.
#
# This route allows users to search for books with a specific `title` and `author`.
# The search is performed by querying the database for books that match the provided `title` and `author` and have upcoming sessions (sessions with a date greater than the current date).
# The function then retrieves the related session information for each book found in the query.
#
# @return: A JSON object containing the details of the book and its upcoming sessions.
# - 'title': The title of the book.
# - 'author': The author of the book.
# - 'page_number': The number of pages in the book.
# - 'release_date': The release date of the book.
# - 'category': The category of the book.
# - 'formation': A list of dictionaries, each containing information about an upcoming session for the book.
#   - 'date': The date of the upcoming session.
#   - 'place': The place of the upcoming session.
# @retval 200: If the book is found and has upcoming sessions.
# @retval 404: If the book is not found in the database.
# @retval 405: If the HTTP method is not allowed (only POST is allowed).
@main.route('/search_books',methods=['POST'])
# @login_required
def search_books():

  try:
        book_id=request.json['id']
        book = Book.query.get(book_id)

        if book:
            sessions = Session.query.filter_by(book_id=book_id).filter(Session.start_date > datetime.now()).all()
            old_sessions = Session.query.filter_by(book_id=book_id).filter(Session.start_date <= datetime.now()).all()
            book_info = {
                'title': book.title,
                'author': book.author,
                'page_number': book.page_number,
                'release_date': book.release_date,
                'category': book.category,
                'img': book.img,
                'desc': book.desc
            }

            if sessions:
                session_info = [{
                    "id": session.id,
                    "title": session.name,
                    "start": session.start_date.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
                    "end": session.end_date.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
                    "teacher": Teacher.query.get(session.teacher_id).email,
                    "pack_id": session.pack_id,
                    "unit_id":session.unit_id,
                    "extendedProps": {
                        "location": session.location.value,
                        "description": session.description,
                        "category": "primary"
                    }
                } for session in sessions]

                book_info['sessions'] = session_info
            else:
                book_info['sessions'] = []
            
            if old_sessions :
                old_session_info = [{
                    "id": session.id,
                    "title": session.name,
                    "start": session.start_date.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
                    "end": session.end_date.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
                    "teacher": Teacher.query.get(session.teacher_id).email,
                    "pack_id": session.pack_id,
                    "unit_id":session.unit_id,
                    "extendedProps": {
                        "location": session.location.value,
                        "description": session.description,
                        "category": "primary"
                    }
                } for session in old_sessions]
                book_info['old_sessions']=old_session_info    
            else:
                book_info['old_sessions']=[]               

            return jsonify(book_info), 200
        else:
            return jsonify({'message': 'Book not found'}), 404
  except Exception as error:
        return jsonify({'message': str(error)}), 500


## @brief Route for retrieving a specific page from a book.
#
# This route allows users to retrieve a specific page from a book with the given `title` and `author`.
# The `page` parameter specifies the page number to retrieve from the book.
# The route uses a `book_inst` instance of the `Book` class to fetch the content of the specified page.
#
# @return: A JSON object containing the content of the requested page.
# - 'content': The content of the requested page from the book.
# @retval 200: If the page is found and the content is retrieved successfully.
# @retval 404: If the book or the requested page is not found in the database.
# @retval 405: If the HTTP method is not allowed (only POST is allowed).
#
"""@main.route('/get_book_page_content',methods=['POST'])
@login_required
def get_book_page_content():
    title=request.json['title']
    author=request.json['author']
    page=request.json['page']
    book_inst=Books(uri,username,password)
    content=book_inst.get_page({'title':title,'author':author,'page':page})
    if content:
        return jsonify({'content':content}),200
    else:
        return jsonify({'message':'Book or page not found'}),404"""
    

@main.route('/get_all_session_list')
def get_all_session_list():
    try:
        all_session=Session.query.all()
        
        session_list=[]
        print(all_session)
        for session in all_session:
            session_list.append({
                'session_name':session.name,
                'session_date':session.date.strftime("%Y-%m-%d"), #format date as string
                'location':session.location.value})
        
        if session_list:
            return jsonify ({'all_session_list':session_list}), 200
        else:
            return jsonify ({'message':'Any session available'}), 404
    except Exception as error:
        return jsonify({'message':str(error)}), 500
    

@main.route('/show_session_details',methods=['POST'])
# @login_required
def show_session_details():
    try:
        token=request.json['id']
        session=Session.query.filter_by(id=token).first()
        if session:
            teacher=Teacher.query.filter_by(id=session.teacher_id).first()
            book=Book.query.filter_by(id=session.book_id).first()
            return jsonify({'date':session.start_date,
                            'location':session.location.value,
                            'teacher':teacher.username,
                            'book':book.title,
                            'capacity':session.capacity,
                            'active':session.active,
                            'name':session.name,
                            'price':session.price,
                            'discount':session.discount,
                            'img':session.img})
        else:
            return jsonify({'message':'No session found'})
    except Exception as error:
        logging.error('An error occurred: %s', error, exc_info=True)
        return jsonify({'message':str(error)}), 500


@main.route('/show_all_pack')
def show_all_pack():
    try:
        age_filter = request.args.get('age') 
        title_search = request.args.get('title') 
        
        age_enum_values = [age.value for age in StatusEnum]

        packs_query = Pack.query
        if age_filter and age_filter in age_enum_values:
            packs_query = packs_query.filter(Pack.age == age_filter)
        if title_search:
            packs_query = packs_query.filter(Pack.title.ilike(f'%{title_search}%'))

        packs = packs_query.filter_by(public=True).all()
       
        if packs:
            packs_info = []
            for pack in packs:
                enrolled = Follow_pack.query.filter_by(pack_id=pack.id).count()
                num_active_codes = Code.query.filter_by(pack_id=pack.id, status=CodeStatusEnum.ACTIVE).count()
                pack_info = {
                    'id': pack.id,
                    'title': pack.title,
                    'level': pack.level,
                    'age': pack.age.value,
                    'price': pack.price,
                    'img': pack.img,
                    'book_number': pack.book_number,
                    'discount': pack.discount,
                    'faq': pack.faq,
                    'codes': num_active_codes ,
                    'enrolled' :enrolled,
                    'duration':pack.duration,
                    'public':pack.public
                }
                packs_info.append(pack_info)

            return jsonify({'packs': packs_info}), 200
        else:
            return jsonify({'message': 'No packs available'}),200
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@main.route('/get_pack_details', methods=['POST'])
def get_pack_details():
    try:
        pack_id = request.json['id']
      
        
        pack = Pack.query.get(pack_id) 
        enrolled = Follow_pack.query.filter_by(pack_id=pack.id).count()
        num_active_codes = Code.query.filter_by(pack_id=pack.id, status=CodeStatusEnum.ACTIVE).count()
        if pack:
            return jsonify({
                'id': pack.id,
                'title': pack.title,
                'level': pack.level,
                'age': pack.age.value,
                'price': pack.price,
                'img': pack.img,
                'book_number': pack.book_number,
                'discount': pack.discount,
                'desc':pack.desc,
                'faq':pack.faq,
                'code':num_active_codes,
                'enrolled' : enrolled,
                'duration':pack.duration,
                'product_id_invoicing_api':pack.product_id_invoicing_api,
                'public':pack.public
            }), 200
        else:
            return jsonify({'message': 'Pack not found'}), 404
    except KeyError:
        return jsonify({'message': 'Invalid input'}), 400


@main.route('/get_books_from_pack', methods=['POST'])
def get_books_from_pack():
    try:
        pack_id = request.json['id']
    except KeyError:
        return jsonify({'message': 'Invalid input'}), 400
    
    pack = Pack.query.get(pack_id)
    
    if pack:
        books_in_pack = (
            db.session.query(Book)
            .join(Book_pack)
            .join(Pack)
            .filter(Pack.id == pack_id)
            .all()
        )
        
        book_list = [
            {  
                'id' : book.id,
                'title': book.title,
                'author': book.author,
                'release_date': book.release_date,
                'page_number': book.page_number,
                'category': book.category,
                'desc' : book.desc,
                'img' :book.img
               
            }
            for book in books_in_pack
        ]
        
        return jsonify({'books_in_pack': book_list}), 200
    else:
        return jsonify({'message': 'Pack not found'}), 404
from flask import request

@main.route('/send_email', methods=['POST'])
def send_email():
    try:
        # Get user input from the request's JSON data
        first_name = request.json.get('first_name')
        last_name = request.json.get('last_name')
        email = request.json.get('email')
        phone = request.json.get('phone')
        subject = request.json.get('subject')
        message = request.json.get('message')

        # Send an email to the customer
        customer_msg = Message(
            subject='Your Email Has Been Sent Successfully',
            sender=ConfigClass.MAIL_USERNAME,
            recipients=[email],
        )

        # Build the email message body for the customer
        customer_html_body = render_template('customer_email_template.html', subject=subject, first_name=first_name, last_name=last_name, email=email, phone=phone, message=message)

        # Send the email to the customer
        customer_msg.html = customer_html_body
        mail.send(customer_msg)

        # Send an email to yourself
        admin_msg = Message(
            subject='New Email Sent',
            sender=ConfigClass.MAIL_USERNAME,
            recipients=[ConfigClass.MAIL_USERNAME],  
        )

        # Build the email message body for the admin
        admin_html_body = render_template('admin_email_template.html', subject=subject, first_name=first_name, last_name=last_name, email=email, phone=phone, message=message)

        # Send the email to yourself
        admin_msg.html = admin_html_body
        mail.send(admin_msg)

        return jsonify({'message': 'Email sent successfully'}), 200

    except Exception as error:
        print(str(error))  # Print the error message for debugging
        return jsonify({'message': 'Something Went Wrong Please Try Again Later .'}), 500

@main.route('/intellect_send_email', methods=['POST'])
def intellect_send_email():
    try:
        # Get user input from the request's JSON data
        first_name = request.json.get('first_name')
        last_name = request.json.get('last_name')
        email = request.json.get('email')
        phone = request.json.get('phone')
        subject = request.json.get('subject')
        message = request.json.get('message')

        # Send an email to the customer
        customer_msg = Message(
            subject='Your Email Has Been Sent Successfully',
            sender=ConfigClass.MAIL_USERNAME,
            recipients=[email],
        )

        # Build the email message body for the customer
        customer_html_body = render_template('intellect_customer_email_template.html', subject=subject, first_name=first_name, last_name=last_name, email=email, phone=phone, message=message)

        # Send the email to the customer
        customer_msg.html = customer_html_body
        mail.send(customer_msg)

        # Send an email to yourself
        admin_msg = Message(
            subject='New Email Sent',
            sender=ConfigClass.MAIL_USERNAME,
            recipients=[ConfigClass.MAIL_USERNAME],  
        )

        # Build the email message body for the admin
        admin_html_body = render_template('intellect_admin_email_template.html', subject=subject, first_name=first_name, last_name=last_name, email=email, phone=phone, message=message)

        # Send the email to yourself
        admin_msg.html = admin_html_body
        mail.send(admin_msg)

        return jsonify({'message': 'Email sent successfully'}), 200

    except Exception as error:
        print(str(error))  # Print the error message for debugging
        return jsonify({'message': 'Something Went Wrong Please Try Again Later .'}), 500