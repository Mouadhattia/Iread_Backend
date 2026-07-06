from models.shcool import Shcool
from models.user_shcool import User_shcool


def get_account_block_message(user):
    """Returns (message, http_status) if this user should be blocked from
    using the app right now (suspended account, or every school they belong
    to is suspended), or None if they're clear to proceed. Super admins
    aren't scoped to a school so only the account-level check applies."""
    if not user.is_active:
        return ('Your account has been suspended. Contact your school administrator.', 403)

    if user.type == 'super_admin':
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
