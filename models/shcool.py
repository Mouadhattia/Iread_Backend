## @file
#@class Shcool
from extensions import db


##
# @brief Table for storing the relationship between users and packs they follow.
#
class Shcool(db.Model):
    __tablename__='shcool'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    suspended_at = db.Column(db.DateTime, nullable=True)
    suspended_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    suspended_reason = db.Column(db.String(500), nullable=True)
    ## @brief Per-school override of the free reader allowance used before any
    # contract exists. NULL means "use PlatformSettings.default_trial_seats".
    # Set explicitly for schools that need grandfathering -- e.g. one carrying
    # a large legacy reader base from before billing existed.
    trial_seats = db.Column(db.Integer, nullable=True)
    def __repr__(self):
        return '< shcool %s >' %self.id

