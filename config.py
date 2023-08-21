## @file
# Database and sending email configuration file

import os

## @brief Configuration of the mysql database and parameters for sending email.
class ConfigClass:
    SQLALCHEMY_DATABASE_URI='mysql://root:''@localhost/iread'
    SECRET_KEY=os.environ.get('SECRET_KEY') or 'password'
    SQLALCHEMY_TRACK_MODIFICATIONS=True

    MAIL_SERVER='smtp.googlemail.com'
    MAIL_PORT=465 #465
    MAIL_USE_SSL=True #True
    MAIL_USE_TLS=False #False
    MAIL_USERNAME='chretienkouete@gmail.com'
    MAIL_PASSWORD='xeevsiazcybdxwpg'
    MAIL_DEBUG=False
    FRONT_URL = 'http://5.135.52.74'
