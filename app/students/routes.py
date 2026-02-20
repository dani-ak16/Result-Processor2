from flask import render_template, request, redirect, url_for
from models.academic import Student, Class, ClassArm, StudentClass
from extensions import db
from utils.academic import get_current_session, get_current_term
from sqlalchemy import func, case
from . import students_bp


# Student Biodata Management
@students_bp.route('/manage-students')
def manage_students():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.id AS arm_id, c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
        """)
    classes = cursor.fetchall()
    
    current_session = get_current_session()
    current_term = get_current_term()

    cursor.execute("SELECT id, name FROM departments WHERE name != 'General' ORDER BY name")
    departments = cursor.fetchall()
    current_year = datetime.now().year
    return render_template('manage_students.html', 
                           classes=classes, 
                           current_year=current_year, 
                           current_term=current_term,
                           current_session=current_session,
                           departments=departments)

@students_bp.route('/')
def view_students():
    class_filter = request.args.get('class_filter', 'all')
    session_filter = request.args.get('session_filter', get_current_session())
    term_filter = request.args.get('term_filter', get_current_term())

    # Validate parameters
    if class_filter != "all":
        try:
            class_filter = int(class_filter)
        except ValueError:
            class_filter = "all"

    # Fetch all class arms for dropdown
    classes = db.session.query(
        ClassArm.id.label('arm_id'),
        Class.name.label('class_name'),
        ClassArm.arm
    ).join(
        Class, ClassArm.class_id == Class.id
    ).order_by(
        Class.id, ClassArm.arm
    ).all()

    # Get distinct sessions
    session_results = db.session.query(
        StudentClass.session.distinct()
    ).order_by(
        StudentClass.session.desc()
    ).all()
    sessions = [row.session for row in session_results]
    if session_filter not in sessions:
        sessions.insert(0, session_filter)

    # Build base query
    query = db.session.query(
        Student.reg_number,
        Student.full_name,
        Student.age,
        Student.photo,
        (Class.name + ' ' + ClassArm.arm).label('class_name'),
        StudentClass.term,
        StudentClass.session
    ).join(
        StudentClass, Student.id == StudentClass.student_id
    ).join(
        ClassArm, StudentClass.class_arm_id == ClassArm.id
    ).join(
        Class, ClassArm.class_id == Class.id
    )

    # Apply filters
    query = query.filter(StudentClass.session == session_filter)
    
    if class_filter != "all":
        query = query.filter(
            StudentClass.term == term_filter,
            StudentClass.class_arm_id == class_filter
        )
    
    # Execute query with ordering
    students = query.order_by(Student.full_name).all()

    return render_template('students/students.html',
                          students=students,
                          classes=classes,
                          sessions=sessions,
                          selected_class=class_filter,
                          selected_session=session_filter,
                          selected_term=term_filter)
