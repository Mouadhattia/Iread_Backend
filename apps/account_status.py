from models.shcool import Shcool
from models.user_shcool import User_shcool


def get_account_block_message(user):
    """Returns (message, http_status) if this user should be blocked from
    using the app right now, or None if they're clear to proceed.

    An account-level suspension (`is_active` False) blocks everyone. Beyond
    that, a *school* closure/suspension only blocks the staff who administer
    that school. Readers and parents keep their Global Reading Passport even
    when their school closes (PRD §7): they stay signed in and retain their
    own reading history, progress, achievements, and certificates plus any
    free/global content — they only lose that school's paid content, which is
    revoked separately at the content-access layer, not here. Super admins
    aren't scoped to a school so only the account-level check applies."""
    if not user.is_active:
        return ('Your account has been suspended. Contact your school administrator.', 403)

    # Readers/parents own their journey independently of any school, so a
    # closed school never strands them from their passport. Super admins are
    # platform-wide.
    if user.type in ('reader', 'parent', 'super_admin'):
        return None

    schools = (
        Shcool.query
        .join(User_shcool, User_shcool.shcool_id == Shcool.id)
        .filter(User_shcool.user_id == user.id)
        .all()
    )
    if schools and not any(school.is_active for school in schools):
        return ('Your school has been suspended. Contact IRead support.', 403)

    return None
