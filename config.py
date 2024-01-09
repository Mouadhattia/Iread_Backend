## @file
# Database and sending email configuration file

import os

## @brief Configuration of the mysql database and parameters for sending email.
class ConfigClass:
    SQLALCHEMY_DATABASE_URI='mysql://root:''@localhost/IRead'
    SECRET_KEY=os.environ.get('SECRET_KEY') or 'password'
    SQLALCHEMY_TRACK_MODIFICATIONS=True
    MAIL_SERVER='smtp.office365.com' 
    MAIL_PORT=587 
    MAIL_USE_SSL=False  
    MAIL_USE_TLS=True 
    MAIL_USERNAME='contact@intellect.education' 
    MAIL_PASSWORD='xyydcyfddsdwfdfn'
    MAIL_DEBUG=False 
    FRONT_URL = 'http://iread.tn'
    API_URL= 'http://localhost:5003'
    QUIZ_API = 'https://quiz.iread.tn/user'
    QUIZ_API_KEY ='65800f77a2ce2e2c88ebd8bd'

    # Set the session lifetime to 1 hour (3600 seconds)
    PERMANENT_SESSION_LIFETIME = 3600