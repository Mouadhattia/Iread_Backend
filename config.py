## @file
# Database and sending email configuration file
from datetime import timedelta
import os

## @brief Configuration of the mysql database and parameters for sending email.
class ConfigClass:
    SQLALCHEMY_DATABASE_URI = 'mysql://root:''@localhost/backup'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'password'
    SQLALCHEMY_TRACK_MODIFICATIONS = True  
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_SSL = False
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'intellect.education.contact@gmail.com'
    MAIL_PASSWORD = 'your_app_specific_password'  # Replace with your Gmail app-specific password
    MAIL_DEBUG = False   
    FRONT_URL = 'http://iread.tn'
    API_URL = 'http://localhost:5003'
    QUIZ_API = 'https://quiz.iread.tn/user'
    QUIZ_API_KEY = '65800f77a2ce2e2c88ebd8bd'
    INVOICING_API = 'https://invoicing-api.iread.tn'
    INVOICING_API_KEY = '65ba69fb713e132120743444'   
    # Set the session lifetime to 1 hour (3600 seconds)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365*100)  # 100 years
