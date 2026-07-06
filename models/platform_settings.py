## @file
# @class PlatformSettings
from datetime import datetime

from extensions import db

SINGLETON_ID = 1


##
# @brief A single-row table of platform-wide toggles, settable by super
# admins only. Starts with just the dictionary-suggestion gate; add more
# boolean columns here if/when more platform-wide toggles are needed.
class PlatformSettings(db.Model):
    __tablename__ = 'platform_settings'

    id = db.Column(db.Integer, primary_key=True)
    require_dictionary_approval = db.Column(db.Boolean, nullable=False, default=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get():
        settings = PlatformSettings.query.get(SINGLETON_ID)
        if not settings:
            settings = PlatformSettings(id=SINGLETON_ID, require_dictionary_approval=False)
            db.session.add(settings)
            db.session.commit()
        return settings

    def __repr__(self):
        return '<PlatformSettings require_dictionary_approval=%s>' % self.require_dictionary_approval
