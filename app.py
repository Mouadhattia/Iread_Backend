## @mainpage Flask Project Documentation
#
# Welcome to the documentation for the Flask project.
# This documentation provides an overview of the project's architecture, modules, and API.
# You can navigate through different sections using the links in the sidebar.
#
# @section intro Introduction
# This project is a Flask-based web application that implements a book management system.
# It allows users to sign up, log in, and manage their reading lists.
# The application has different user roles, including Reader, Teacher, and Admin.
# Readers can add books to their reading lists, Teachers can manage book sessions, and Admins can manage users.
#
# @section installation Installation
# To run this project, follow the steps below:
# - Clone the repository: `git clone https://github.com/jeanChretienKouete/IntellectEnglish.git`
# - Create a virtual environment: `python -m venv venv`
# - Activate the virtual environment: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
# - Install the required packages: `pip install -r requirements.txt`
# - Set up the database: `flask db upgrade`
# - Run the application: `flask run`
#
# @section usage Usage
# Once the application is up and running, you can access it in your web browser at `http://localhost:5000`.
# The application provides the following main features:
# - User Registration: New users can sign up and create an account.
# - User Login: Existing users can log in using their credentials.
# - Book Management: Users can view, add, and remove books from their reading lists.
# - Session Management: Teachers can schedule book sessions and manage attendees.
# - User Management: Admins can manage user accounts and roles.
#
# @section api API Reference
# For detailed information about the application's API, refer to the API documentation.
# The API documentation provides endpoints, request methods, and response formats for different functionalities.
# You can access the API documentation through the link in the sidebar.
#
# @page homepage Home Page
# @section homesection Home Section
# This is the home page of the documentation.
# You can use the links in the sidebar to explore different sections of the documentation.
# The documentation provides an overview of the project's architecture, modules, and API.
# For information on how to run the project, navigate to the Installation section.
# To learn about the application's features, refer to the Usage section.
# If you need details about the API, access the API documentation in the API Reference section.
# Happy exploring!
#
# @section contact Contact
# For any inquiries or support, please contact the development team at <intellectgabes@gmail.com>.


## @file
from flask import Flask
from flask_cors import CORS
from models.user import User,Reader,Teacher,Admin
from models.book import Book
from models.book_pack import Book_pack
from models.session import Session
from models.follow_pack import Follow_pack
from models.pack import Pack
from models.follow_session import Follow_session
from models.teacher_postulate import Teacher_postulate
from config import ConfigClass
from extensions import mail,login_manager,db
from flask_migrate import Migrate

## @brief Create the Flask application instance.
app=Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*", "supports_credentials": True}})






## @brief Configure the application using the configuration class from the config.py file.
app.config.from_object(ConfigClass)

## @brief Initialize the email extension.
mail.init_app(app)

## @brief Initialize the login manager extension.
login_manager.init_app(app)

## @brief Create the application context and create all tables defined in the models directory
# @param app: The application instance.
db.init_app(app)

## @brief Database migration.
migrate=Migrate(app,db)

from apps.reader.routes import reader
from apps.teacher.routes import teacher
from apps.admin.routes import admin
from apps.main.routes import main

@app.route('/')
def home():
    return "<h1>Welcome to the home page</h1>"

## @brief Merge the 'admin','main' and 'auth' blueprints into the app (the application).
app.register_blueprint(reader)
app.register_blueprint(teacher)
app.register_blueprint(admin)
app.register_blueprint(main)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)  # Change the port to your desired port number