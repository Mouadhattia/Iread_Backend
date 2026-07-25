from extensions import db
from datetime import datetime


class AdminAuditLog(db.Model):
    __tablename__ = "admin_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=True)
    actor_username = db.Column(db.String(150), nullable=True)
    actor_role = db.Column(db.String(30), nullable=True)
    action = db.Column(db.String(60), nullable=False)
    target_type = db.Column(db.String(60), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<AdminAuditLog {self.action} {self.target_type}={self.target_id} by {self.actor_id}>'
