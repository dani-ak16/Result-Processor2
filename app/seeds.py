from extensions import db 
from models import (
    Skill, 
    PrincipalComment,
    Department,
    Subject,
    DepartmentSubject,
    ClassArm,
    ClassSubjectRequirement,
    Class
)


def initialize_subjects_and_departments(school_id):

    # -----------------------------
    # Departments
    # -----------------------------

    departments = [
        ("Junior", "junior", "All subjects for junior classes"),
        ("Science", "senior", "Science department for senior classes"),
        ("Arts/Humanities", "senior", "Arts and Humanities department"),
        ("Commercial", "senior", "Commercial/Business department")
    ]

    for name, level, desc in departments:

        exists = Department.query.filter_by(
            name=name,
            level=level
        ).first()

        if not exists:
            dept = Department(
                name=name,
                level=level,
                description=desc
            )
            db.session.add(dept)

    db.session.commit()


    # -----------------------------
    # Subjects
    # -----------------------------

    subjects_data = [

        # Junior
        ("Mathematics", "junior", True),
        ("English", "junior", True),
        ("Basic Science", "junior", False),
        ("Basic Technology", "junior", False),
        ("Business Studies", "junior", False),
        ("Social Studies", "junior", False),
        ("Cultural and Creative Arts", "junior", False),
        ("Igbo Language", "junior", False),
        ("Yoruba Language", "junior", False),
        ("French Language", "junior", False),
        ("Information and Communication Technology", "junior", False),
        ("Music", "junior", False),
        ("History", "junior", False),
        ("Physical and Health Education", "junior", False),
        ("Civic Education", "junior", True),
        ("Agricultural Science", "junior", False),
        ("Security Education", "junior", False),
        ("Christian Religious Studies", "junior", False),
        ("Literature in English", "junior", False),
        ("Diction", "junior", False),

        # Senior Core
        ("Mathematics", "senior", True),
        ("English", "senior", True),
        ("Civic Education", "senior", True),

        # Science
        ("Physics", "senior", False),
        ("Chemistry", "senior", False),
        ("Biology", "senior", False),
        ("Further Mathematics", "senior", False),
        ("Agricultural Science", "senior", False),
        ("Geography", "senior", False),
        ("Technical Drawing", "senior", False),
        ("Information and Communication Technology", "senior", False),
        ("Data Processing", "senior", False),

        # Arts
        ("Literature in English", "senior", False),
        ("Government", "senior", False),
        ("History", "senior", False),
        ("Christian Religious Studies", "senior", False),
        ("Visual Arts", "senior", False),
        ("Yoruba Language", "senior", False),
        ("Igbo Language", "senior", False),
        ("French Language", "senior", False),

        # Commercial
        ("Economics", "senior", False),
        ("Commerce", "senior", False),
        ("Financial Accounting", "senior", False)
    ]


    for name, level, core in subjects_data:

        exists = Subject.query.filter_by(
            name=name,
            level=level
        ).first()

        if not exists:

            subject = Subject(
                name=name,
                level=level,
                is_common_core=core,
                school_id=school_id
            )

            db.session.add(subject)

    db.session.commit()


    # -----------------------------
    # Build Lookup Dictionaries
    # -----------------------------

    departments = {
        f"{d.name}_{d.level}": d
        for d in Department.query.all()
    }

    subjects = {
        f"{s.name}_{s.level}": s
        for s in Subject.query.all()
    }


    # -----------------------------
    # Department → Subjects
    # -----------------------------

    def add_dept_subject(dept, subj, compulsory):

        exists = DepartmentSubject.query.filter_by(
            department_id=dept.id,
            subject_id=subj.id
        ).first()

        if not exists:

            link = DepartmentSubject(
                department_id=dept.id,
                subject_id=subj.id,
                is_compulsory=compulsory
            )

            db.session.add(link)


    # Junior

    junior = departments.get("Junior_junior")

    for key, subj in subjects.items():

        if key.endswith("_junior"):
            add_dept_subject(junior, subj, True)


    # Science

    science = departments.get("Science_senior")

    science_subjects = [
        "Mathematics_senior",
        "English_senior",
        "Civic Education_senior",
        "Physics_senior",
        "Chemistry_senior"
    ]


    for key in science_subjects:

        if key in subjects:

            compulsory = key in [
                "Mathematics_senior",
                "English_senior",
                "Civic Education_senior",
                "Physics_senior",
                "Chemistry_senior"
            ]

            add_dept_subject(
                science,
                subjects[key],
                compulsory
            )


    # Arts

    arts = departments.get("Arts/Humanities_senior")

    arts_subjects = [
        "Mathematics_senior",
        "English_senior",
        "Civic Education_senior",
        "Literature in English_senior"
    ]


    for key in arts_subjects:

        if key in subjects:

            compulsory = key in [
                "Mathematics_senior",
                "English_senior",
                "Civic Education_senior",
                "Literature in English_senior"
            ]

            add_dept_subject(
                arts,
                subjects[key],
                compulsory
            )


    # Commercial

    commercial = departments.get("Commercial_senior")

    commercial_subjects = [
        "Mathematics_senior",
        "English_senior",
        "Civic Education_senior",
        "Economics_senior"
    ]


    for key in commercial_subjects:

        if key in subjects:

            compulsory = key in [
                "Mathematics_senior",
                "English_senior",
                "Civic Education_senior",
                "Economics_senior"
            ]

            add_dept_subject(
                commercial,
                subjects[key],
                compulsory
            )


    db.session.commit()


    # -----------------------------
    # Assign to Class Arms
    # -----------------------------

    class_arms = db.session.query(ClassArm, Class)\
        .join(Class)\
        .all()


    for arm, cls in class_arms:

        name = cls.name.lower()


        if "jss" in name:
            dept = junior

        elif "sss" in name:

            if "science" in name:
                dept = science

            elif "arts" in name:
                dept = arts

            elif "commercial" in name:
                dept = commercial

            else:
                dept = science

        else:
            continue


        dept_subjects = DepartmentSubject.query.filter_by(
            department_id=dept.id
        ).all()


        for ds in dept_subjects:

            exists = ClassSubjectRequirement.query.filter_by(
                class_arm_id=arm.id,
                subject_id=ds.subject_id
            ).first()

            if not exists:

                req = ClassSubjectRequirement(
                    class_arm_id=arm.id,
                    subject_id=ds.subject_id,
                    is_compulsory=ds.is_compulsory
                )

                db.session.add(req)


    db.session.commit()


    print("✅ Subjects and departments initialized.")

def initialize_class_subject_requirements():
    """Set up subject requirements for each class arm"""
    db = get_db()
    cursor = db.cursor()
    
    # Get all class arms and their levels
    cursor.execute("""
        SELECT ca.id as arm_id, c.name as class_name, c.level, ca.arm
        FROM class_arms ca
        JOIN classes c ON ca.class_id = c.id
    """)
    class_arms = cursor.fetchall()
    
    for class_arm in class_arms:
        class_level = class_arm['level']  # 'JSS' or 'SSS'
        arm_id = class_arm['arm_id']
        
        if class_level == "JSS":
            # Junior classes get all junior subjects
            cursor.execute("""
                INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory)
                SELECT ?, s.id, 1
                FROM subjects s
                WHERE s.level = 'junior'
            """, (arm_id,))
        else:
            # Senior classes get common core subjects + department subjects
            # This will be handled when students are assigned to departments
            
            # For now, add all subjects to all senior classes
            #CHANGE LATER
            cursor.execute("""
                INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory)
                SELECT ?, s.id, s.is_common_core
                FROM subjects s
                WHERE s.level = 'senior'
            """, (arm_id,))
    
    db.commit()
    print("Class subject requirements initialized")

def seed_initial_data(school_id):

    # Prevent reseeding
    if Skill.query.first():
        return

    print("Seeding initial database data...")


    # Skills
    skills = [
        "Coding", "Photography", "Fascinator", "Music",
        "Dance", "Maintenance and Repair", "Chess"
    ]

    for name in skills:
        db.session.add(Skill(name=name))


    # Principal comments
    comment_rows = [
        (30, 39, "This performance is well below expectation..."),
        (40, 50, "This is not a true reflection..."),
        (50, 60, "A satisfactory performance..."),
        (60, 70, "A good effort..."),
        (70, 80, "Good work this term..."),
        (80, 90, "Excellent performance...")
    ]

    for min_a, max_a, text in comment_rows:
        db.session.add(
            PrincipalComment(
                min_average=min_a,
                max_average=max_a,
                comment=text
            )
        )


    # Classes
    classes = [
        ("JSS 1", "JSS"),
        ("JSS 2", "JSS"),
        ("JSS 3", "JSS"),
        ("SSS 1", "SSS"),
        ("SSS 2", "SSS"),
        ("SSS 3", "SSS")
    ]

    for name, level in classes:
        db.session.add(Class(name=name, level=level, school_id=school_id))


    # Class arms
    class_arms = [
        (1, "GOLD"), (1, "DIAMOND"),
        (2, "GOLD"), (2, "DIAMOND"),
        (3, "GOLD"), (3, "DIAMOND"),
        (4, "GOLD"), (4, "DIAMOND"),
        (5, "GOLD"), (5, "DIAMOND"),
        (6, "MASTERS")
    ]

    for class_id, arm in class_arms:
        db.session.add(
            ClassArm(class_id=class_id, arm=arm)
        )


    # Extra setup
    initialize_subjects_and_departments(school_id)
    # initialize_class_subject_requirements()


    db.session.commit()

    print("✅ Database seeded successfully.")
