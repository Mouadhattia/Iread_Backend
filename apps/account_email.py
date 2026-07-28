## @file
# @brief Transactional emails about a reader's account standing, as opposed to
# a school's billing (see apps/billing_email.py).
#
# The one thing every message here has to get across is that an iRead account
# outlives the school that introduced it: leaving a school is not leaving the
# platform, and the Global Reading Passport -- reading history, words learned,
# streaks, achievements, certificates -- travels with the reader (PRD §6/§7).
# Families read "removed" as "deleted" unless told otherwise, so the reassurance
# is the subject line, not a footnote.
from apps.emailer import send_html_email
from config import ConfigClass
from models.user import User


##
# @brief The name to greet a reader/parent by, preferring whatever they chose
# to be called over the raw username.
def display_name_for(user):
    if user is None:
        return None
    return (user.display_name or user.username or '').strip() or None


##
# @brief The Parent account that manages this reader, if any.
#
# Reader.parent_id points at the owning Parent's User.id; self-registered
# readers have none, and that is a normal, silent case.
def get_parent_for_reader(reader):
    parent_id = getattr(reader, 'parent_id', None)
    if not parent_id:
        return None
    return User.query.get(parent_id)


##
# @brief Where a signed-out recipient should land to carry on reading.
def _reader_dashboard_url():
    front_url = (ConfigClass.FRONT_URL or '').rstrip('/')
    return f'{front_url}/reader/dashboard' if front_url else None


def _parent_dashboard_url():
    front_url = (ConfigClass.FRONT_URL or '').rstrip('/')
    return f'{front_url}/parent/dashboard' if front_url else None


##
# @brief Tell a reader -- and the parent who manages them, if there is one --
# that a school has offboarded them, and that their account is untouched.
#
# A household's Parent and their first Reader are created together at signup
# and can share a single mailbox. When that happens only the parent-addressed
# version is sent: it names the child and covers both readers of that inbox,
# whereas the reader-addressed version arriving at a parent's mailbox reads as
# if the parent themselves had been removed.
#
# @param reader   The offboarded Reader.
# @param school   The Shcool they were removed from.
# @param parent   Their Parent, or None. Resolved by the caller so the lookup
#                 happens while the row is still loaded.
# @return dict of which messages were handed to the mail server.
def send_removed_from_school_emails(reader, school, parent=None):
    school_name = (school.name if school else None) or 'your school'
    reader_name = display_name_for(reader)
    parent_name = display_name_for(parent)

    reader_email = (reader.email or '').strip() if reader else ''
    parent_email = (parent.email or '').strip() if parent else ''
    shared_mailbox = bool(
        reader_email and parent_email and reader_email.lower() == parent_email.lower()
    )

    results = {'reader': False, 'parent': False}

    if parent_email:
        results['parent'] = send_html_email(
            subject=f'{reader_name or "Your child"} has been removed from {school_name}',
            recipients=[parent_email],
            template='school_removal_parent.html',
            category='Account email',
            parent_name=parent_name,
            reader_name=reader_name or 'Your child',
            school_name=school_name,
            dashboard_url=_parent_dashboard_url(),
        )

    if reader_email and not shared_mailbox:
        results['reader'] = send_html_email(
            subject=f'You have been removed from {school_name} — your iRead account stays open',
            recipients=[reader_email],
            template='school_removal_reader.html',
            category='Account email',
            reader_name=reader_name,
            school_name=school_name,
            dashboard_url=_reader_dashboard_url(),
        )

    return results
