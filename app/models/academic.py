from extensions import db
from datetime import datetime

# ---------------- CLASSES ---------------- #

class Class(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )

    name = db.Column(db.String(50), unique=True, nullable=False)

    level = db.Column(db.String(10), nullable=False)

    arms = db.relationship("ClassArm", backref="class_", lazy=True)


class ClassArm(db.Model):
    __tablename__ = "class_arms"

    id = db.Column(db.Integer, primary_key=True)

    class_id = db.Column(
        db.Integer,
        db.ForeignKey("classes.id"),
        nullable=False
    )

    arm = db.Column(db.String(10), nullable=False)

    # students = db.relationship("Student", backref="class_arm", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("class_id", "arm"),
    )


# ---------------- STUDENTS ---------------- #

class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )

    reg_number = db.Column(db.String(50), unique=True)

    full_name = db.Column(db.String(150), nullable=False)

    age = db.Column(db.Integer)

    gender = db.Column(db.String(10))

    photo = db.Column(db.String(255))

    status = db.Column(db.String(20), default="active")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id")
    )


class StudentClass(db.Model):
    __tablename__ = "student_classes"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id"),
        nullable=False
    )

    class_arm_id = db.Column(
        db.Integer,
        db.ForeignKey("class_arms.id"),
        nullable=False
    )

    session = db.Column(db.String(20), nullable=False)

    term = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "class_arm_id", "session", "term"
        ),
    )

# ---------------- SUBJECTS ---------------- #

class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )

    name = db.Column(db.String(100), nullable=False)

    level = db.Column(db.String(10), nullable=False)

    is_common_core = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("name", "level"),
    )

class ClassSubjectRequirement(db.Model):
    __tablename__ = "class_subject_requirements"

    id           = db.Column(db.Integer, primary_key=True)
    class_arm_id = db.Column(db.Integer, db.ForeignKey("class_arms.id"), nullable=False)
    subject_id   = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    is_compulsory = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("class_arm_id", "subject_id"),
    )

    class_arm = db.relationship("ClassArm")

class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), unique=True, nullable=False)

    level = db.Column(db.String(10), nullable=False)

    description = db.Column(db.Text)


class DepartmentSubject(db.Model):
    __tablename__ = "department_subjects"

    id = db.Column(db.Integer, primary_key=True)

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id")
    )

    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("subjects.id")
    )

    is_compulsory = db.Column(db.Boolean, default=True)
