from extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class School(db.Model):
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False, unique=True)
    code = db.Column(db.String(50), unique=True)

    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)

    logo = db.Column(db.String(255))

    active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship("User", backref="school", lazy=True)
    students = db.relationship("Student", backref="school", lazy=True)

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )

    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120))

    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(30), default="staff")
    # admin, teacher, staff

    is_active = db.Column(db.Boolean, default=True)

    last_login = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ------------------
    # Auth helpers
    # ------------------

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
