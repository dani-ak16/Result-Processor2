from models.academic import Subject
from datetime import datetime
from sqlalchemy import func
from models.academic import Subject, ClassSubjectRequirement, StudentClass, Class, ClassArm
from models.assessment import Score
from extensions import db

def get_current_term():
    month = datetime.now().month

    if month <= 4:
        return 2
    elif month <= 8:
        return 3
    return 1


def get_current_session():
    year = datetime.now().year
    term = get_current_term()

    if term != 1:
        return f"{year-1}/{year}"
    else:
        return f"{year}/{year+1}"


# def get_subjects_by_class_arm(class_arm_id):

#     subjects = (
#         Subject.query
#         .join(ClassSubjectRequirement)
#         .filter(
#             ClassSubjectRequirement.class_arm_id == class_arm_id
#         )
#         .all()
#     )

#     return subjects

def get_subjects_by_class_arm(class_arm_id):
    """Get all subjects required for a class arm"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT s.id, s.name, s.level, s.is_common_core, csr.is_compulsory
        FROM subjects s
        JOIN class_subject_requirements csr ON s.id = csr.subject_id
        WHERE csr.class_arm_id = ?
        ORDER BY s.is_common_core DESC, s.name
    """, (class_arm_id,))
    
    return cursor.fetchall()

def get_subjects_by_department(department_id):
    """Get all subjects for a department"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT s.id, s.name, s.level, ds.is_compulsory
        FROM subjects s
        JOIN department_subjects ds ON s.id = ds.subject_id
        WHERE ds.department_id = ?
        ORDER BY ds.is_compulsory DESC, s.name
    """, (department_id,))
    
    return cursor.fetchall()

def get_class_status():
    """Get status of which classes have student data for the current year"""
    current_session = get_current_session()
    
    # Subquery: Count students per class arm for current session
    class_arm_students = db.session.query(
        StudentClass.class_arm_id,
        func.count(StudentClass.student_id.distinct()).label('student_count')
    ).filter(
        StudentClass.session == current_session
    ).group_by(
        StudentClass.class_arm_id
    ).subquery()
    
    # Main query: Get all class arms with student counts
    results = db.session.query(
        ClassArm.id.label('arm_id'),
        Class.name.label('class_name'),
        ClassArm.arm,
        func.coalesce(class_arm_students.c.student_count, 0).label('student_count')
    ).join(
        Class, ClassArm.class_id == Class.id
    ).outerjoin(
        class_arm_students, ClassArm.id == class_arm_students.c.class_arm_id
    ).order_by(
        Class.id, ClassArm.arm
    ).all()
    
    # Build the data structure
    classes_with_data = []
    for row in results:
        classes_with_data.append({
            'arm_id': row.arm_id,
            'class_name': row.class_name,
            'arm': row.arm,
            'has_data': row.student_count > 0,
            'student_count': row.student_count
        })
    
    return classes_with_data

def get_best_student_match(class_arm_id, session, full_name):
    """Simple approach that always returns one student or None"""
    search_name = full_name.strip()
    
    db = get_db()
    cursor = db.cursor()

    # Get all students in the class
    cursor.execute("""
        SELECT s.*, c.name || ' ' || a.arm AS class_name
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        JOIN class_arms a ON sc.class_arm_id = a.id
        JOIN classes c ON a.class_id = c.id
        WHERE sc.class_arm_id = ? AND sc.session = ?
    """, (class_arm_id, session))
    
    all_students = cursor.fetchall()
    
    if not all_students:
        return None
    
    # Convert to list of dictionaries
    students = [dict(student) for student in all_students]
    
    search_lower = search_name.lower()
    
    # Try exact match first
    for student in students:
        if student['full_name'].lower() == search_lower:
            return student
    
    # Try contains match
    contains_matches = [s for s in students if search_lower in s['full_name'].lower()]
    if len(contains_matches) == 1:
        return contains_matches[0]
    
    # Try reverse contains (search term contains student name)
    reverse_matches = [s for s in students if s['full_name'].lower() in search_lower]
    if len(reverse_matches) == 1:
        return reverse_matches[0]
    
    # Try word-based matching
    search_words = set(search_lower.split())
    word_matches = []
    for student in students:
        student_words = set(student['full_name'].lower().split())
        if search_words.intersection(student_words):
            word_matches.append(student)
    
    if len(word_matches) == 1:
        return word_matches[0]
    
    return None

def grade_from_average(avg):
    if avg >= 75:
        return "A+"
    elif avg >= 65:
        return "B+"
    elif avg >= 60:
        return "C+"

def get_upload_status(class_arm_id, term, session, report_type='full_term'):
    """Get upload status for all subjects in a class"""
    
    # Get all subjects required for this class
    subjects = db.session.query(
        Subject.id,
        Subject.name,
        Subject.is_common_core,
        ClassSubjectRequirement.is_compulsory
    ).join(
        ClassSubjectRequirement, Subject.id == ClassSubjectRequirement.subject_id
    ).filter(
        ClassSubjectRequirement.class_arm_id == class_arm_id
    ).order_by(
        Subject.name
    ).all()

    # Get number of students in the class
    total_students = db.session.query(
        func.count(StudentClass.id)
    ).filter(
        StudentClass.class_arm_id == class_arm_id,
        StudentClass.session == session,
        StudentClass.term == term
    ).scalar() or 0

    upload_status = []

    for subject in subjects:
        # Count how many students have scores for this subject and report type
        uploaded_count = db.session.query(
            func.count(func.distinct(Score.student_id))
        ).join(
            StudentClass, Score.student_id == StudentClass.student_id
        ).filter(
            StudentClass.class_arm_id == class_arm_id,
            Score.subject_id == subject.id,
            Score.term == term,
            Score.session == session,
            Score.report_type == report_type
        ).scalar() or 0

        # Calculate completion percentage
        completion_percentage = 0
        if total_students > 0:
            completion_percentage = (uploaded_count / total_students) * 100

        # Determine status
        if total_students == 0:
            status = 'no_students'
        elif uploaded_count == total_students:
            status = 'complete'
        elif uploaded_count > 0:
            status = 'partial'
        else:
            status = 'pending'

        upload_status.append({
            'subject_id': subject.id,
            'subject_name': subject.name,
            'is_required': subject.is_compulsory,
            'uploaded_count': uploaded_count,
            'total_students': total_students,
            'completion_percentage': completion_percentage,
            'status': status
        })

    return upload_status
