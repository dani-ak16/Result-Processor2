from flask import render_template, request, redirect, url_for
from extensions import db
from . import assessments_bp

@assessments_bp.route('/attendance/summary/<int:class_arm_id>/<int:term>/<path:session>')
def attendance_summary(class_arm_id, term, session):
    db = get_db()
    cursor = db.cursor()
    
    # Get class information
    cursor.execute("""
        SELECT c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        WHERE a.id = ?
    """, (class_arm_id,))
    class_info = cursor.fetchone()
    
    # Get students in this class
    cursor.execute("""
        SELECT s.id, s.reg_number, s.full_name, s.photo
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.session = ?
        ORDER BY s.full_name
    """, (class_arm_id, session))
    students = cursor.fetchall()
    
    # Get existing attendance data
    attendance_data = {}
    total_school_days = None
    
    for student in students:
        cursor.execute("""
            SELECT days_present, days_absent, days_late, total_school_days
            FROM attendance_summary 
            WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
        """, (student['id'], class_arm_id, term, session))
        result = cursor.fetchone()
        if result:
            attendance_data[student['id']] = dict(result)
            # Use the total_school_days from the first student record
            if total_school_days is None:
                total_school_days = result['total_school_days']
    
    return render_template('attendance_summary.j2',
                         class_info=class_info,
                         students=students,
                         attendance_data=attendance_data,
                         total_school_days=total_school_days,
                         class_arm_id=class_arm_id,
                         term=term,
                         session=session)

@assessments_bp.route('/attendance/submit-summary', methods=['POST'])
def submit_attendance_summary():
    class_arm_id = request.form['class_arm_id']
    term = request.form['term']
    session = get_current_session()
    total_school_days = int(request.form['total_school_days'])
    
    db = get_db()
    cursor = db.cursor()
    
    # Get all students in this class
    cursor.execute("""
        SELECT s.id 
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.session = ?
    """, (class_arm_id, session))
    students = cursor.fetchall()
    
    for student in students:
        student_id = student['id']
        
        # Extract attendance data for this student
        days_present = int(request.form.get(f'present_{student_id}', 0))
        days_absent = int(request.form.get(f'absent_{student_id}', 0))
        days_late = int(request.form.get(f'late_{student_id}', 0))
        
        # Insert or update attendance summary
        cursor.execute('''INSERT OR REPLACE INTO attendance_summary 
                          (student_id, class_arm_id, term, session, 
                           days_present, days_absent, days_late, total_school_days) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                       (student_id, class_arm_id, term, session,
                        days_present, days_absent, days_late, total_school_days))
    
    db.commit()
    
    return redirect(url_for('class_teacher_class_view', 
                          class_arm_id=class_arm_id, 
                          session=session, 
                          term=term))

@assessments_bp.route('/bulk/<int:class_arm_id>/<int:term>/<path:session>')
def bulk_assessments(class_arm_id, term, session):
    db = get_db()
    cursor = db.cursor()
    
    # Get class information
    cursor.execute("""
        SELECT c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        WHERE a.id = ?
    """, (class_arm_id,))
    class_info = cursor.fetchone()
    
    # Get students in this class
    cursor.execute("""
        SELECT s.id, s.reg_number, s.full_name, s.photo
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.session = ?
        ORDER BY s.full_name
    """, (class_arm_id, session))
    students = cursor.fetchall()
    
    # ---- get student averages -----------------------------------------
    cursor.execute("""
        SELECT 
            s.id AS student_id,
            ROUND(AVG(sc.total_score), 2) AS average_score
        FROM students s
        JOIN scores sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ?
        AND sc.term = ?
        AND sc.session = ?
        AND sc.report_type = 'full_term'
        GROUP BY s.id
    """, (class_arm_id, term, session))

    averages = {
        row['student_id']: row['average_score']
        for row in cursor.fetchall()
    }

    # Get existing assessment data
    assessment_data = {}
    for student in students:
        cursor.execute("""
            SELECT * FROM student_assessments 
            WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
        """, (student['id'], class_arm_id, term, session))
        result = cursor.fetchone()
        if result:
            assessment_data[student['id']] = dict(result)

    cursor.execute("""
        SELECT * FROM principal_comments
        ORDER BY min_average
    """)
    principal_comments = cursor.fetchall()

    cursor.execute("SELECT * FROM skills ORDER BY name")
    skills = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM student_skills
        WHERE class_arm_id=? AND term=? AND session=?
    """, (class_arm_id, term, session))

    skill_data = {}
    for row in cursor.fetchall():
        skill_data.setdefault(row["student_id"], {})[row["skill_id"]] = row["score"]

    return render_template('bulk_assessments.j2',
                         class_info=class_info,
                         students=students,
                         averages=averages,
                         assessment_data=assessment_data,
                         class_arm_id=class_arm_id,
                         principal_comments=principal_comments,
                         skills=skills,
                         skill_data=skill_data,
                         term=term,
                         current_session=session)

@assessments_bp.route('/submit-bulk', methods=['POST'])
def submit_bulk_assessments():
    class_arm_id = request.form['class_arm_id']
    term = request.form['term']
    session = get_current_session()
    
    db = get_db()
    cursor = db.cursor()
    
    # Get all students in this class
    cursor.execute("""
        SELECT s.id 
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.session = ?
    """, (class_arm_id, session))
    students = cursor.fetchall()

    for student in students:
        student_id = student['id']
        
        # Extract assessment data for this student
        handwriting = request.form.get(f'handwriting_{student_id}')
        sports_participation = request.form.get(f'sports_participation_{student_id}')
        practical_skills = request.form.get(f'practical_skills_{student_id}')
        punctuality = request.form.get(f'punctuality_{student_id}')
        politeness = request.form.get(f'politeness_{student_id}')
        neatness = request.form.get(f'neatness_{student_id}')
        class_teacher_comment = request.form.get(f'class_teacher_comment_{student_id}', '')
        principal_comment = request.form.get(f'principal_comment_{student_id}', '')

        # Convert to integers if they exist
        handwriting = int(handwriting) if handwriting else None
        sports_participation = int(sports_participation) if sports_participation else None
        practical_skills = int(practical_skills) if practical_skills else None
        punctuality = int(punctuality) if punctuality else None
        politeness = int(politeness) if politeness else None
        neatness = int(neatness) if neatness else None
        
        # Insert or update assessment record
        cursor.execute('''INSERT OR REPLACE INTO student_assessments 
                          (student_id, class_arm_id, term, session, 
                           handwriting, sports_participation, practical_skills,
                           punctuality, politeness, neatness, class_teacher_comment, principal_comment) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (student_id, class_arm_id, term, session,
                        handwriting, sports_participation, practical_skills,
                        punctuality, politeness, neatness, class_teacher_comment, principal_comment))

        skill_id = request.form.get(f"skill_id_{student['id']}")
        raw_score = request.form.get(f"skill_score_{student['id']}")

        try:
            skill_id = int(skill_id)
            score = int(raw_score) if raw_score not in (None, "") else 0
        except ValueError:
            continue

        cursor.execute("""
            INSERT OR REPLACE INTO student_skills
            (student_id, class_arm_id, term, session, skill_id, score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            student["id"],
            class_arm_id,
            term,
            session,
            skill_id,
            score
        ))

    db.commit()
    
    return redirect(url_for('class_teacher_class_view', 
                          class_arm_id=class_arm_id, 
                          session=session, 
                          term=term))

@assessments_bp.route('/attendance/redirect')
def attendance_sheet_redirect():
    class_arm_id = request.args.get('class_arm_id')
    date = request.args.get('date')
    term = request.args.get('term')
    
    if not all([class_arm_id, date, term]):
        return redirect(url_for('teacher.class_teacher_portal'))
    
    return redirect(url_for('attendance_sheet', 
                        class_arm_id=class_arm_id, 
                        date=date, 
                        term=term))