## @file
# Database and sending email configuration file
from datetime import timedelta
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    ## python-dotenv is a convenience, not a requirement. On a server where it
    # is not installed (FTP deploys with no pip access), settings still come
    # from real environment variables exactly as before -- the app must never
    # fail to boot over an optional helper.
    def load_dotenv(*args, **kwargs):
        return False

## @brief Load .env from the project root before any setting is read.
#
# Must run at import time, ahead of the ConfigClass body: those os.environ
# lookups execute when the class is defined, so a later load would be too late.
#
# Real environment variables win over .env (override=False), so a server that
# sets STRIPE_SECRET_KEY in its own process environment is not overridden by a
# stale file left on disk.
#
# This covers every entry point at once -- `flask run`, app.py, `flask db`, and
# the scripts/ jobs -- because they all import config.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=False)

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
    ADMIN_FRONT_URL = os.environ.get('ADMIN_FRONT_URL') or 'https://admin.iread.education'
    API_URL = 'https://api.iread.education'
    QUIZ_API = 'https://quiz.iread.education/'
    QUIZ_API_KEY = '65800f77a2ce2e2c88ebd8bd'
    INVOICING_API = 'https://invoicing.iread.education'
    INVOICING_API_KEY = '65ba69fb713e132120743444'
    ## @brief Hard-block school pack activations once a school hits its
    # licensed seat limit. Off until the seat ledger has been backfilled and
    # verified against real data -- with it off, seats are still recorded and
    # reported, just never refused.
    SEAT_ENFORCEMENT_ENABLED = (os.environ.get('SEAT_ENFORCEMENT_ENABLED') or '').lower() in ('1', 'true', 'yes')
    ## @brief Platform billing currency. iRead is an Irish company.
    BILLING_CURRENCY = os.environ.get('BILLING_CURRENCY') or 'EUR'

    ## @brief Allow a super admin to apply database migrations from the web UI.
    #
    # Needed because production is deployed over FTP with no shell access. It
    # is off by default and should be switched back off once a deploy is done:
    # an always-on "change the database schema" endpoint is a large piece of
    # attack surface to leave standing for the sake of occasional convenience.
    ALLOW_WEB_MIGRATIONS = (os.environ.get('ALLOW_WEB_MIGRATIONS') or '').lower() in ('1', 'true', 'yes')

    ## @brief Stripe credentials. Environment only -- never commit these.
    # Without STRIPE_SECRET_KEY the billing service stays dormant and every
    # Stripe-backed endpoint returns a clear "not configured" error instead of
    # failing deep inside the SDK.
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY') or ''
    ## @brief Signing secret for /billing/stripe/webhook. An unverified webhook
    # endpoint lets anyone mark any invoice paid, so the handler refuses to
    # process anything when this is unset.
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') or ''
    ## @brief Whether iRead itself is VAT-registered.
    #
    # A business that is not VAT-registered must not charge VAT, must not show
    # a VAT amount on its invoices, and must not call them VAT invoices. Until
    # registration happens this stays false and invoices go out net, with a
    # note explaining why no VAT is shown.
    #
    # Registration is not optional forever: Irish VAT registration becomes
    # obligatory once turnover passes the services threshold (in the low tens
    # of thousands of euro -- confirm the current figure with an accountant),
    # and supplying services to businesses in other EU member states generally
    # forces registration regardless of turnover. At these contract values that
    # threshold arrives after only a handful of schools, so treat this as a
    # switch that will be flipped, not a permanent state.
    PLATFORM_VAT_REGISTERED = (os.environ.get('PLATFORM_VAT_REGISTERED') or '').lower() in ('1', 'true', 'yes')
    ## @brief iRead's own VAT number, shown on invoices once registered.
    PLATFORM_VAT_NUMBER = os.environ.get('PLATFORM_VAT_NUMBER') or ''
    ## @brief The supplier's registered identity, printed on receipts.
    #
    # A receipt has to say who took the money, under the trading name the
    # company is actually registered as. These are deliberately empty by
    # default: the Irish registered name and address are still being
    # finalised, and an invented one on a financial document is worse than an
    # absent one, so the receipt template omits the block until they are set.
    PLATFORM_LEGAL_NAME = os.environ.get('PLATFORM_LEGAL_NAME') or ''
    PLATFORM_ADDRESS = os.environ.get('PLATFORM_ADDRESS') or ''
    PLATFORM_COMPANY_NUMBER = os.environ.get('PLATFORM_COMPANY_NUMBER') or ''
    ## @brief Where a recipient of a transactional email should write back.
    # Replies to the sending mailbox already reach a human, so that is the
    # default rather than a second address nobody watches.
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL') or MAIL_USERNAME
    ## @brief Let Stripe Tax compute VAT. Meaningless until we are registered
    # and have entered a tax registration in the Stripe dashboard -- with no
    # registration Stripe computes 0% anyway, so leaving it on would only
    # produce a misleading "VAT €0.00" line on every invoice.
    STRIPE_TAX_ENABLED = (
        (os.environ.get('STRIPE_TAX_ENABLED') or '').lower() in ('1', 'true', 'yes')
        or PLATFORM_VAT_REGISTERED
    )
    ## @brief Printed on invoices while not VAT-registered, so a school's
    # finance office understands the absence of a VAT line.
    INVOICE_NO_VAT_NOTE = os.environ.get('INVOICE_NO_VAT_NOTE') or (
        'No VAT charged: the supplier is not registered for VAT.'
    )
    ## @brief Days a school gets to pay before an invoice is overdue.
    INVOICE_DUE_DAYS = int(os.environ.get('INVOICE_DUE_DAYS') or 30)
    ## @brief Root of the self-hosted per-school file store. Everything a school
    # uploads (story audio/images, book covers and PDFs, pack images) lives under
    # `<SCHOOL_STORAGE_DIR>/school_<id>/<category>/`, with platform-owned assets
    # under `platform/`. Replaces the former Cloudinary hosting, so this path
    # must be on persistent, backed-up disk -- losing it loses every asset.
    SCHOOL_STORAGE_DIR = os.environ.get('SCHOOL_STORAGE_DIR') or os.path.join(os.getcwd(), 'storage')
    ## @brief Absolute origin the stored media URLs are built from, e.g.
    # `https://api.iread.education`. The URLs go into the database (book.img,
    # pack.img, user.img, ...) and are read by every frontend, so they must be
    # absolute -- a relative `/media/...` would resolve against whichever app
    # rendered it, not the API. Empty falls back to the request's own host,
    # which is correct for local development but not for a queue/CLI context.
    PUBLIC_MEDIA_BASE_URL = (os.environ.get('PUBLIC_MEDIA_BASE_URL') or '').rstrip('/')
    ## @brief Default disk allowance per school, in MB. Overridable per school
    # via Shcool.storage_quota_mb so a large customer can be raised without
    # lifting the limit for everyone.
    SCHOOL_STORAGE_QUOTA_MB = int(os.environ.get('SCHOOL_STORAGE_QUOTA_MB') or 5120)
    ## @brief Per-file ceilings for the storage manager, by kind of asset.
    MAX_MEDIA_IMAGE_UPLOAD_MB = int(os.environ.get('MAX_MEDIA_IMAGE_UPLOAD_MB') or 10)
    MAX_MEDIA_AUDIO_UPLOAD_MB = int(os.environ.get('MAX_MEDIA_AUDIO_UPLOAD_MB') or 50)
    MAX_MEDIA_DOCUMENT_UPLOAD_MB = int(os.environ.get('MAX_MEDIA_DOCUMENT_UPLOAD_MB') or 50)
    ## @brief Legacy upload roots. New uploads go to SCHOOL_STORAGE_DIR, but
    # rows written before the migration still hold absolute paths under these,
    # so they stay configured for reads.
    STORY_UPLOAD_DIR = os.environ.get('STORY_UPLOAD_DIR') or os.path.join(os.getcwd(), 'uploads', 'stories')
    MAX_STORY_UPLOAD_MB = int(os.environ.get('MAX_STORY_UPLOAD_MB') or 50)
    AUDIOBOOK_UPLOAD_DIR = os.environ.get('AUDIOBOOK_UPLOAD_DIR') or os.path.join(os.getcwd(), 'uploads', 'audio-books')
    MAX_AUDIOBOOK_IMAGE_UPLOAD_MB = int(os.environ.get('MAX_AUDIOBOOK_IMAGE_UPLOAD_MB') or 10)
    MAX_AUDIOBOOK_AUDIO_UPLOAD_MB = int(os.environ.get('MAX_AUDIOBOOK_AUDIO_UPLOAD_MB') or 50)
    AUDIOBOOK_ALIGNMENT_MODEL = os.environ.get('AUDIOBOOK_ALIGNMENT_MODEL') or 'base'
    AUDIOBOOK_ALIGNMENT_DEVICE = os.environ.get('AUDIOBOOK_ALIGNMENT_DEVICE') or 'cpu'
    AUDIOBOOK_FFMPEG_DIR = os.environ.get('AUDIOBOOK_FFMPEG_DIR') or ''
    AUDIOBOOK_SENTENCE_PAUSE_MS = int(os.environ.get('AUDIOBOOK_SENTENCE_PAUSE_MS') or 700)
    AUDIOBOOK_LINE_BREAK_PAUSE_MS = int(os.environ.get('AUDIOBOOK_LINE_BREAK_PAUSE_MS') or 1200)
    CALL_JWT_SECRET = os.environ.get('CALL_JWT_SECRET') or 'intellect'
    JITSI_APP_ID = os.environ.get('JITSI_APP_ID') or 'intellect'
    JITSI_DOMAIN = os.environ.get('JITSI_DOMAIN') or 'meeting.intellect.tn'
    JITSI_AUD = os.environ.get('JITSI_AUD') or 'jitsi'
    JITSI_TOKEN_TTL_SECONDS = int(os.environ.get('JITSI_TOKEN_TTL_SECONDS') or 36000)
    # Set the session lifetime to 1 hour (3600 seconds)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365*100)  # 100 years
