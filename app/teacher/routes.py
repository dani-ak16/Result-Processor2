from flask import render_template, request, redirect, url_for
from extensions import db
from sqlalchemy import func
from models.academic import ClassArm, Class, Student, StudentClass, Department, Subject
from models.assessment import StudentAssessment, Score
from utils.academic import get_current_session, get_current_term, get_upload_status, get_class_status
from datetime import datetime
from . import teacher_bp


@teacher_bp.route('/class-teacher')
def class_teacher_portal():
    current_session = get_current_session()
    current_term = get_current_term()
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Get all class arms with their class info using a join
    classes = db.session.query(
        ClassArm.id.label('arm_id'),
        Class.name.label('class_name'),
        ClassArm.arm,
        Class.level
    ).join(
        Class, ClassArm.class_id == Class.id
    ).order_by(
        Class.id, ClassArm.arm
    ).all()
    
    return render_template('teacher/class_teacher_portal.html', 
                         classes=classes,
                         current_session=current_session,
                         current_term=current_term,
                         current_date=current_date)

@teacher_bp.route('/class/<int:class_arm_id>/<path:session>/<int:term>')
def class_teacher_class_view(class_arm_id, session, term):
    
    # Get class information
    class_info = db.session.query(
        Class.name.label('class_name'),
        ClassArm.arm,
        Class.level
    ).join(
        Class, ClassArm.class_id == Class.id
    ).filter(
        ClassArm.id == class_arm_id
    ).first()
    
    # Get students in this class
    students = db.session.query(
        Student.id,
        Student.reg_number,
        Student.full_name,
        Student.age,
        Student.gender,
        Student.photo,
        Student.department_id,
        Department.name.label('department_name')
    ).join(
        StudentClass, Student.id == StudentClass.student_id
    ).outerjoin(
        Department, Student.department_id == Department.id
    ).filter(
        StudentClass.class_arm_id == class_arm_id,
        StudentClass.session == session
    ).order_by(
        Student.full_name
    ).all()
    
    print(students)

    # Get assessment data for all students
    assessment_data = {}
    for student in students:
        assessment = StudentAssessment.query.filter_by(
            student_id=student.id,
            class_arm_id=class_arm_id,
            term=term,
            session=session
        ).first()
        assessment_data[student.id] = assessment

    half_term_status = get_upload_status(class_arm_id, term, session, 'half_term')
    full_term_status = get_upload_status(class_arm_id, term, session, 'full_term')

    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('teacher/class_teacher_class_view.html',
                         class_info=class_info,
                         students=students,
                         half_term_status=half_term_status,
                         full_term_status=full_term_status,
                         assessment_data=assessment_data,
                         class_arm_id=class_arm_id,
                         session=session,
                         term=term,
                         current_date=current_date)

@teacher_bp.route('/subject-teacher')
def subject_teacher_portal():
    
    # Get all subjects
    subjects = Subject.query.order_by(Subject.name).all()

    # Get class status
    classes_with_data = get_class_status()

    # Get last 10 uploads
    recent_uploads = db.session.query(
        Subject.name.label('subject_name'),
        Class.name.label('class_name'),
        ClassArm.arm,
        Score.term,
        Score.session,
        func.max(Score.created_at).label('date_uploaded')
    ).join(
        Subject, Score.subject_id == Subject.id
    ).join(
        ClassArm, Score.class_arm_id == ClassArm.id
    ).join(
        Class, ClassArm.class_id == Class.id
    ).group_by(
        Subject.name,
        Class.name,
        ClassArm.arm,
        Score.term,
        Score.session
    ).order_by(
        func.max(Score.created_at).desc()
    ).limit(10).all()

    current_session = get_current_session()

    return render_template(
        'teacher/subject_teacher_portal.html',
        subjects=subjects,
        classes=classes_with_data,
        current_session=current_session,
        recent_uploads=recent_uploads
    )

