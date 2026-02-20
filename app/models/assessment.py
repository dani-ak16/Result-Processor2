from extensions import db
from datetime import datetime


# ---------------- SCORES ---------------- #

class Score(db.Model):
    __tablename__ = "scores"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )
    
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))

    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))

    class_arm_id = db.Column(db.Integer, db.ForeignKey("class_arms.id"))

    term = db.Column(db.Integer, nullable=False)

    session = db.Column(db.String(20), nullable=False)

    ca1_score = db.Column(db.Float, default=0)
    ca2_score = db.Column(db.Float, default=0)
    ca3_score = db.Column(db.Float, default=0)
    ca4_score = db.Column(db.Float, default=0)

    exam_score = db.Column(db.Float, default=0)

    total_score = db.Column(db.Float, default=0)

    report_type = db.Column(
        db.Enum("half_term", "full_term", name="report_type"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    approved = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "subject_id",
            "class_arm_id", "term",
            "session", "report_type"
        ),
    )


# ---------------- ASSESSMENTS ---------------- #

class StudentAssessment(db.Model):
    __tablename__ = "student_assessments"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))

    class_arm_id = db.Column(db.Integer, db.ForeignKey("class_arms.id"))

    term = db.Column(db.Integer)
    session = db.Column(db.String(20))

    handwriting = db.Column(db.Integer)
    sports_participation = db.Column(db.Integer)
    practical_skills = db.Column(db.Integer)

    punctuality = db.Column(db.Integer)
    politeness = db.Column(db.Integer)
    neatness = db.Column(db.Integer)

    class_teacher_comment = db.Column(db.Text)
    principal_comment = db.Column(db.Text)
