## @file
# Database and sending email configuration file
from datetime import timedelta
import os

## @brief Configuration of the mysql database and parameters for sending email.
class ConfigClass:
    SQLALCHEMY_DATABASE_URI = 'mysql://root:''@localhost/iread'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'password'
    SQLALCHEMY_TRACK_MODIFICATIONS = True  
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_SSL = False
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'intellect.education.contact@gmail.com'
    MAIL_PASSWORD = 'gvwdouhlcazzytnp'  # Replace with your Gmail app-specific password
    MAIL_DEBUG = False   
    FRONT_URL = 'https://iread.education'
    API_URL = 'https://api.iread.education'
    QUIZ_API = 'https://quiz.iread.education/user'
    QUIZ_API_KEY = '65800f77a2ce2e2c88ebd8bd'
    INVOICING_API = 'https://invoicing.iread.education'
    INVOICING_API_KEY = '65ba69fb713e132120743444'   
    STORY_UPLOAD_DIR = os.environ.get('STORY_UPLOAD_DIR') or os.path.join(os.getcwd(), 'uploads', 'stories')
    MAX_STORY_UPLOAD_MB = int(os.environ.get('MAX_STORY_UPLOAD_MB') or 50)
    AUDIOBOOK_UPLOAD_DIR = os.environ.get('AUDIOBOOK_UPLOAD_DIR') or os.path.join(os.getcwd(), 'uploads', 'audio-books')
    MAX_AUDIOBOOK_IMAGE_UPLOAD_MB = int(os.environ.get('MAX_AUDIOBOOK_IMAGE_UPLOAD_MB') or 10)
    MAX_AUDIOBOOK_AUDIO_UPLOAD_MB = int(os.environ.get('MAX_AUDIOBOOK_AUDIO_UPLOAD_MB') or 50)
    AUDIOBOOK_ALIGNMENT_MODEL = os.environ.get('AUDIOBOOK_ALIGNMENT_MODEL') or 'base'
    AUDIOBOOK_ALIGNMENT_DEVICE = os.environ.get('AUDIOBOOK_ALIGNMENT_DEVICE') or 'cpu'
    AUDIOBOOK_FFMPEG_DIR = os.environ.get('AUDIOBOOK_FFMPEG_DIR') or ''
    CALL_JWT_SECRET = os.environ.get('CALL_JWT_SECRET') or 'intellect'
    JITSI_APP_ID = os.environ.get('JITSI_APP_ID') or 'intellect'
    JITSI_DOMAIN = os.environ.get('JITSI_DOMAIN') or 'meeting.intellect.tn'
    JITSI_AUD = os.environ.get('JITSI_AUD') or 'jitsi'
    JITSI_TOKEN_TTL_SECONDS = int(os.environ.get('JITSI_TOKEN_TTL_SECONDS') or 36000)
    # Set the session lifetime to 1 hour (3600 seconds)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365*100)  # 100 years
