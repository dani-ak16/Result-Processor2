from extensions import db


class PrincipalComment(db.Model):
    __tablename__ = "principal_comments"

    id = db.Column(db.Integer, primary_key=True)

    min_average = db.Column(db.Float, nullable=False)

    max_average = db.Column(db.Float, nullable=False)

    comment = db.Column(db.Text, nullable=False)


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), unique=True)


class StudentSkill(db.Model):
    __tablename__ = "student_skills"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))

    class_arm_id = db.Column(db.Integer, db.ForeignKey("class_arms.id"))

    term = db.Column(db.Integer)
    session = db.Column(db.String(20))

    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"))

    score = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "skill_id",
            "class_arm_id", "term", "session"
        ),
    )
