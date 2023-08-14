## @file
# @brief This file initializes and imports Flask extensions.
# It sets up the necessary instances of Flask extensions such as Mail, LoginManager, and SQLAlchemy.

from flask_mail import Mail
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

## @var mail
# @brief An instance of Flask-Mail extension used for handling email functionality in the Flask application.
mail=Mail()

## @var login_manager
# @brief An instance of Flask-Login extension used for handling user authentication and session management.
login_manager=LoginManager()

## @var db
# @brief An instance of Flask-SQLAlchemy extension used for handling database interactions in the Flask application.
db=SQLAlchemy()