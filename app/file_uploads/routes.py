from flask import render_template, request, redirect, url_for
import pandas as pd
import numpy as np
from extensions import db
from sqlalchemy import func
from models.academic import Subject, Class, ClassArm, StudentClass, Student, Department
from models.assessment import Score
from utils.academic import get_current_session
from . import uploads_bp

def process_half_term_upload(filepath, subject_id, class_arm_id, term, session):
    errors = []
    success_count = 0
    db = get_db()

    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        # df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        df.columns = df.columns.str.strip().str.lower()

        column_mapping = {
            'ca1': 'ca1_score',
            'ca2': 'ca2_score',
            'ca3': 'ca3_score',
            'ca4': 'ca4_score',
            'exam': 'exam_score',
            'total': 'total_score'
        }
        df.rename(columns=column_mapping, inplace=True)

        required_cols = {'full_name', 'ca1_score', 'ca2_score'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return errors, success_count

        cursor = db.cursor()
        subject_name = cursor.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()['name']

        for _, row in df.iterrows():
            try:
                full_name = row['full_name'].strip()
                
                # Get CA scores
                ca1_score = float(row['ca1_score']) if not pd.isna(row['ca1_score']) else 0
                ca2_score = float(row['ca2_score']) if not pd.isna(row['ca2_score']) else 0
                
                # Validate scores
                if not (0 <= ca1_score <= 5):
                    errors.append(f"Invalid CA1 score for {full_name}: {ca1_score}. Must be between 0-5")
                    continue
                if not (0 <= ca2_score <= 5):
                    errors.append(f"Invalid CA2 score for {full_name}: {ca2_score}. Must be between 0-5")
                    continue

                # Calculate total score for half-term
                total_score = ca1_score + ca2_score

                # Find student
                cursor.execute("""
                    SELECT s.id, s.department_id
                    FROM students s
                    JOIN student_classes sc ON s.id = sc.student_id
                    WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ? AND s.full_name = ?
                """, (class_arm_id, session, term, full_name))

                student_row = cursor.fetchone()
                if not student_row:
                    errors.append(f"Student not found in this class: {full_name}")
                    continue

                student_id = student_row['id']
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Insert or update half-term scores
                cursor.execute('''INSERT OR REPLACE INTO scores 
                                  (student_id, subject_id, class_arm_id, term, session,
                                   ca1_score, ca2_score, total_score, report_type, created_at) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (student_id, subject_id, class_arm_id, term, session,
                                ca1_score, ca2_score, total_score, 'half_term', now))

                success_count += 1
                
            except Exception as e:
                errors.append(f"Error processing {full_name}: {str(e)}")

        db.commit()

    except Exception as e:
        errors.append(f"File processing error: {str(e)}")

    return errors, success_count

def process_full_term_upload(filepath, subject_id, class_arm_id, term, session):
    errors = []
    success_count = 0

    try:
        # ------------------------------------------------------------------
        # 1. Read the file
        # ------------------------------------------------------------------
        if filepath.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath, engine='openpyxl')

        # Normalise column names
        df.columns = df.columns.str.strip().str.lower()

        # ------------------------------------------------------------------
        # 2. Rename columns to what the code expects
        # ------------------------------------------------------------------
        column_mapping = {
            'ca1': 'ca1_score', 'ca2': 'ca2_score',
            'ca3': 'ca3_score', 'ca4': 'ca4_score',
            'exam': 'exam_score', 'total': 'total_score'
        }
        df.rename(columns=column_mapping, inplace=True)

        required_cols = {'full_name', 'ca1_score', 'ca2_score',
                         'ca3_score', 'ca4_score', 'exam_score'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return errors, success_count

        # ------------------------------------------------------------------
        # 3. Verify that the subject actually exists
        # ------------------------------------------------------------------
        subject = Subject.query.get(subject_id)
        if not subject:
            errors.append(f"Subject with id={subject_id} not found in the database.")
            return errors, success_count
        subject_name = subject.name

        # ------------------------------------------------------------------
        # 4. Process each row
        # ------------------------------------------------------------------
        for idx, row in df.iterrows():
            try:
                full_name = str(row['full_name']).strip()
                if not full_name or full_name.lower() == 'nan':
                    errors.append(f"Row {idx+2}: Empty or invalid full_name")
                    continue

                def read_score(val):
                    """
                    Returns:
                    - float score if valid
                    - None if blank / NaN / invalid
                    """
                    try:
                        if pd.isna(val):
                            return None
                        return float(val)
                    except:
                        return None

                ca1_score = read_score(row['ca1_score'])
                ca2_score = read_score(row['ca2_score'])
                ca3_score = read_score(row['ca3_score'])
                ca4_score = read_score(row['ca4_score'])
                exam_score = read_score(row['exam_score'])

                # ---- find the student in the correct class/term/session ----------
                student_result = db.session.query(
                    Student.id,
                    Student.department_id
                ).join(
                    StudentClass, Student.id == StudentClass.student_id
                ).filter(
                    StudentClass.class_arm_id == class_arm_id,
                    StudentClass.session == session,
                    StudentClass.term == term,
                    func.lower(func.trim(Student.full_name)) == func.lower(func.trim(full_name))
                ).first()

                if not student_result:
                    errors.append(f"Student not enrolled in this class/term/session: {full_name}")
                    continue

                student_id = student_result.id

                # ---- insert / replace the score ----------------------------------
                now = datetime.now()
                
                if ca1_score is not None and ca2_score is not None and ca3_score is not None and ca4_score is not None and exam_score is not None:

                    # ---- validation --------------------------------------------------
                    if not (0 <= ca1_score <= 5):
                        errors.append(f"{full_name}: CA1 {ca1_score} (must be 0-5)")
                        continue
                    if not (0 <= ca2_score <= 5):
                        errors.append(f"{full_name}: CA2 {ca2_score} (must be 0-5)")
                        continue
                    if not (0 <= ca3_score <= 5):
                        errors.append(f"{full_name}: CA3 {ca3_score} (must be 0-5)")
                        continue
                    if not (0 <= ca4_score <= 5):
                        errors.append(f"{full_name}: CA4 {ca4_score} (must be 0-5)")
                        continue
                    if not (0 <= exam_score <= 80):
                        errors.append(f"{full_name}: Exam {exam_score} (must be 0-80)")
                        continue
                    
                    total_score = ca1_score + ca2_score + ca3_score + ca4_score + exam_score

                    # Check if score already exists
                    existing_score = Score.query.filter_by(
                        student_id=student_id,
                        subject_id=subject_id,
                        class_arm_id=class_arm_id,
                        term=term,
                        session=session,
                        report_type='full_term'
                    ).first()

                    if existing_score:
                        # Update existing score
                        existing_score.ca1_score = ca1_score
                        existing_score.ca2_score = ca2_score
                        existing_score.ca3_score = ca3_score
                        existing_score.ca4_score = ca4_score
                        existing_score.exam_score = exam_score
                        existing_score.total_score = total_score
                        existing_score.created_at = now
                    else:
                        # Create new score
                        new_score = Score(
                            student_id=student_id,
                            subject_id=subject_id,
                            class_arm_id=class_arm_id,
                            term=term,
                            session=session,
                            ca1_score=ca1_score,
                            ca2_score=ca2_score,
                            ca3_score=ca3_score,
                            ca4_score=ca4_score,
                            exam_score=exam_score,
                            total_score=total_score,
                            report_type='full_term',
                            created_at=now
                        )
                        db.session.add(new_score)

                    success_count += 1

            except Exception as row_err:
                errors.append(f"Row {idx+2} ({full_name}): {str(row_err)}")

        # Commit all changes at once
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        errors.append(f"File processing error: {str(e)}")

    return errors, success_count


def process_student_upload(filepath, class_arm_id, session, term):
    errors = []
    success_count = 0

    try:
        # Load file
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

        # Required columns
        if 'full_name' not in df.columns:
            return ["Missing required column: full_name"], 0

        # Fetch class + arm info
        class_info = db.session.query(
            Class.id.label('class_id'),
            Class.name.label('class_name'),
            Class.level,
            ClassArm.arm
        ).join(
            ClassArm, Class.id == ClassArm.class_id
        ).filter(
            ClassArm.id == class_arm_id
        ).first()

        if not class_info:
            return ["Invalid class arm ID"], 0

        class_name = class_info.class_name
        class_level = class_info.level   # JSS or SSS
        arm = class_info.arm

        # Get existing students in this class/session/term
        existing_results = db.session.query(
            func.lower(func.trim(Student.full_name)).label('lower_name')
        ).join(
            StudentClass, Student.id == StudentClass.student_id
        ).filter(
            StudentClass.class_arm_id == class_arm_id,
            StudentClass.session == session,
            StudentClass.term == term
        ).all()

        existing_students = {row.lower_name for row in existing_results}

        processed_names = set()
        new_students = []

        # Process rows
        for _, row in df.iterrows():
            full_name = str(row['full_name']).strip()
            if not full_name:
                continue

            lname = full_name.lower()

            if lname in processed_names:
                errors.append(f"Duplicate in file skipped: {full_name}")
                continue
            processed_names.add(lname)

            if lname in existing_students:
                errors.append(f"Already exists skipped: {full_name}")
                continue

            # Extract optional fields
            gender = None
            if 'gender' in df.columns and not pd.isna(row.get('gender', None)):
                val = str(row['gender']).strip().lower()
                if val in ['m', 'male', 'boy']: gender = "Male"
                if val in ['f', 'female', 'girl']: gender = "Female"

            dept_name = None
            if 'department' in df.columns and not pd.isna(row.get('department', None)):
                dept_name = str(row['department']).strip()

            new_students.append({
                'full_name': full_name,
                'age': int(row['age']) if 'age' in df.columns and not pd.isna(row.get('age', None)) else None,
                'gender': gender,
                'department': dept_name
            })

        if not new_students:
            return ["No new students to add."], 0

        # ===== Generate reg-number prefix =====
        session_parts = session.split("/")
        session_short = session_parts[0][-2:] + session_parts[1][:2]

        class_abbr = class_name.replace(" ", "").upper()
        arm_abbr = arm[0].upper()
        prefix = f"{class_abbr}{arm_abbr}-{session_short}-{term}-"

        # ===== Get highest existing index for this class-arm-session-term =====
        max_index_result = db.session.query(
            func.max(func.cast(func.substr(Student.reg_number, -3), db.Integer))
        ).filter(
            Student.reg_number.like(prefix + "%")
        ).scalar()

        start_index = (max_index_result + 1) if max_index_result else 1

        # ===== Insert new students =====
        for i, student in enumerate(new_students, start=start_index):
            full_name = student['full_name']
            age = student['age']
            gender = student['gender']
            dept_name = student['department']

            # Department assignment
            department_id = None

            if class_level == "JSS":
                dept = Department.query.filter_by(name='Junior').first()
                department_id = dept.id if dept else None

            else:  # SSS student
                if dept_name:
                    dept_lower = dept_name.lower()

                    if any(k in dept_lower for k in ['sci', 'bio', 'chem', 'phy']):
                        dept = Department.query.filter_by(name='Science').first()
                    elif any(k in dept_lower for k in ['art', 'human', 'lit', 'gov', 'history']):
                        dept = Department.query.filter_by(name='Arts/Humanities').first()
                    elif any(k in dept_lower for k in ['comm', 'bus', 'acct', 'acc', 'eco']):
                        dept = Department.query.filter_by(name='Commercial').first()
                    else:
                        dept = None
                    
                    if dept:
                        department_id = dept.id

                # Default senior dept
                if not department_id:
                    dept = Department.query.filter_by(name='Science').first()
                    department_id = dept.id if dept else None

            # ===== Generate reg number =====
            reg_number = generate_reg_number(class_name, arm, session, term, i)

            # Create new student
            new_student_obj = Student(
                reg_number=reg_number,
                full_name=full_name,
                age=age,
                gender=gender,
                photo=None,
                department_id=department_id
            )
            db.session.add(new_student_obj)
            db.session.flush()  # Flush to get the student_id before commit

            student_id = new_student_obj.id

            # Create class membership
            student_class = StudentClass(
                student_id=student_id,
                class_arm_id=class_arm_id,
                session=session,
                term=term
            )
            db.session.add(student_class)

            success_count += 1

        # Commit all changes at once
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        errors.append(f"File processing error: {str(e)}")

    return errors, success_count


@uploads_bp.route('/students', methods=['POST'])
def upload_students():
    class_arm_id = request.form['class_arm_id']
    session = request.form['session']  # Changed from year to session
    term = request.form['term']  # Added term

    if 'file' not in request.files:
        return redirect(url_for('manage_students'))

    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('manage_students'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        errors, success_count = process_student_upload(filepath, class_arm_id, session, term)

        if errors:
            return render_template('upload_error.html', errors=errors, success_count=success_count)

        return render_template('upload_success.html',
                              success_count=success_count,
                              message=f"{success_count} student profiles created")

    return redirect(url_for('manage_students'))

@uploads_bp.route('/half-term-results')
def upload_half_term_results():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cursor.fetchall()

    cursor.execute("""
        SELECT a.id AS arm_id, c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
    """)
    classes = cursor.fetchall()

    current_session = get_current_session()

    return render_template('upload_half_term_results.html',
                          subjects=subjects,
                          classes=classes,
                          current_session=current_session)

@uploads_bp.route('/full-term-results')
def upload_full_term_results():
    if request.method == 'POST':
        subject_id = request.form['subject_id']
        class_arm_id = request.form['class_arm_id']
        term = request.form['term']
        session = request.form['session']

        if 'file' not in request.files:
            return redirect(url_for('uploads.upload_full_term_results'))

        file = request.files['file']
        if file.filename == '':
            return redirect(url_for('uploads.upload_full_term_results'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            errors, success_count = process_full_term_upload(filepath, subject_id, class_arm_id, term, session)

            if errors:
                return render_template('upload_error.html', errors=errors, success_count=success_count)

            return render_template('upload_success.html',
                                  success_count=success_count,
                                  message=f"{success_count} full-term scores uploaded")

        return redirect(url_for('uploads.upload_full_term_results'))
    
    # GET request - show the upload form
    subjects = Subject.query.order_by(Subject.name).all()

    classes = db.session.query(
        ClassArm.id.label('arm_id'),
        Class.name.label('class_name'),
        ClassArm.arm
    ).join(
        Class, ClassArm.class_id == Class.id
    ).order_by(
        Class.id, ClassArm.arm
    ).all()

    current_session = get_current_session()

    return render_template('upload_full_term_results.html',
                          subjects=subjects,
                          classes=classes,
                          current_session=current_session)

@uploads_bp.route('/student-photos')
def student_photos():
    db = get_db()
    cursor = db.cursor()
    
    # Get all classes for dropdown
    cursor.execute("""
        SELECT a.id AS arm_id, c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
    """)
    classes = cursor.fetchall()
    
    selected_class = request.args.get('class_arm_id')
    students = []
    session = get_current_session()

    if selected_class:
        # Get students in selected class for current year
        cursor.execute("""
            SELECT s.reg_number, s.full_name, s.photo, 
                   c.name AS class_name, a.arm
            FROM students s
            JOIN student_classes sc ON s.id = sc.student_id
            JOIN class_arms a ON sc.class_arm_id = a.id
            JOIN classes c ON a.class_id = c.id
            WHERE sc.class_arm_id = ? AND sc.session = ?
            ORDER BY s.full_name
        """, (selected_class, session))
        students = cursor.fetchall()
    
    return render_template('photo_management.html',
                         classes=classes,
                         students=students,
                         selected_class=selected_class)

@uploads_bp.route('/student-photo/<reg_number>', methods=['POST'])
def upload_student_photo(reg_number):
    db = get_db()
    cursor = db.cursor()
    
    # Get student name for success message
    cursor.execute("SELECT full_name FROM students WHERE reg_number = ?", (reg_number,))
    student = cursor.fetchone()
    student_name = student['full_name'] if student else "Student"
    
    if 'photo' not in request.files:
        return render_template('error.html', message="No file selected")
    
    file = request.files['photo']
    if file.filename == '':
        return render_template('error.html', message="No file selected")
    
    if file and allowed_photo_file(file.filename):
        try:
            # Ensure upload directory exists
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'photos')
            os.makedirs(upload_dir, exist_ok=True)

            # Extract file extension
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'

            # Create filename from reg number
            filename = secure_filename(f"{reg_number}.{file_ext}")
            photo_path = os.path.join(upload_dir, filename)

            # Save original uploaded file
            file.save(photo_path)

            # Create compressed filename
            compressed_filename = f"compressed_{reg_number}.jpg"
            compressed_path = os.path.join(upload_dir, compressed_filename)

            # Compress (IMPORTANT: use the actual saved photo_path)
            compress_image(
                img_path=photo_path,
                output_path=compressed_path
            )

            # Store ONLY the compressed filename in DB
            cursor.execute(
                "UPDATE students SET photo=? WHERE reg_number=?",
                (compressed_filename, reg_number)
            )

            db.commit()
            
            # Redirect based on where the upload came from
            redirect_to = request.form.get('redirect_to', 'class_teacher')
            
            if redirect_to == 'photo_management':
                class_arm_id = request.form.get('class_arm_id')
                return redirect(url_for('student_photos') + f'?class_arm_id={class_arm_id}')
            elif redirect_to == 'class_view':
                class_arm_id = request.form.get('class_arm_id')
                session = get_current_session()
                term = get_current_term()
                return redirect(url_for('class_teacher_class_view', 
                                      class_arm_id=class_arm_id, 
                                      session=session, 
                                      term=term))
            else:
                return redirect(url_for('class_teacher_portal'))
                
        except Exception as e:
            return render_template('error.html', message=f"Error uploading photo: {str(e)}")
    
    return render_template('error.html', message="Invalid file type. Please upload JPG, JPEG, or PNG files.")

@uploads_bp.route('/photos/<filename>')
def serve_uploaded_photo(filename):
    """Serve uploaded photos from the uploads directory"""
    try:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), filename)
    except FileNotFoundError:
        # Return a default image or 404 if the file doesn't exist
        return "Image not found", 404
    
@uploads_bp.route('/preview-results', methods=['POST'])
def preview_results():
    """Show preview of uploaded result file before confirming."""
    try:
        report_type = request.form.get("report_type")  # 'half_term' or 'full_term'
        subject_id = request.form.get("subject_id")
        class_arm_id = request.form.get("class_arm_id")
        term = int(request.form.get("term"))
        session = request.form.get("session")

        # Validate form inputs
        if not all([report_type, subject_id, class_arm_id, term, session]):
            return render_template("error.html", message="Missing required fields.")

        # Validate file
        if 'file' not in request.files:
            return render_template("error.html", message="No file uploaded.")

        file = request.files['file']
        if file.filename == '':
            return render_template("error.html", message="Empty file name.")

        # Save file temporarily
        temp_filename = f"temp_{datetime.now().timestamp()}_{secure_filename(file.filename)}"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_path)

        # Load DataFrame
        df = pd.read_excel(temp_path) if temp_path.endswith(".xlsx") else pd.read_csv(temp_path)
        df.columns = df.columns.str.strip().str.lower()

        # Column requirements
        required_cols = {'full_name', 'ca1', 'ca2'} if report_type == "half_term" else {
            'full_name', 'ca1', 'ca2', 'ca3', 'ca4', 'exam'
        }

        # Detect missing columns
        missing = required_cols - set(df.columns)
        if missing:
            return render_template(
                "upload_error.html",
                errors=[f"Missing required columns: {', '.join(missing)}"],
                success_count=0
            )

        # Check existing scores that might be overwritten
        db = get_db()
        cursor = db.cursor()
        overwrite_warnings = []

        cursor.execute("""
            SELECT sub.name
            FROM subjects sub
            WHERE sub.id=?
        """, (subject_id,)
        )
        subject = cursor.fetchone()

        cursor.execute("""
            SELECT a.id AS arm_id, c.name AS class_name, a.arm
            FROM class_arms a
            JOIN classes c ON a.class_id = c.id
            WHERE a.id = ?
        """, (class_arm_id,))
        class_data = cursor.fetchone()

        for name in df['full_name']:

            # 1. Lookup student ID from name
            cursor.execute("""
                SELECT s.id
                FROM students s
                JOIN student_classes sc ON s.id = sc.student_id
                WHERE sc.class_arm_id=? AND sc.session=? AND sc.term=? AND s.full_name=?
            """, (class_arm_id, session, term, name.strip()))

            student = cursor.fetchone()
            if not student:
                continue  # or collect as an error
            
            student_id = student['id']

            # 2. Check if scores already exist for this student
            cursor.execute("""
                SELECT 1 FROM scores
                WHERE student_id=? AND subject_id=? AND class_arm_id=? AND term=? AND session=?
            """, (student_id, subject_id, class_arm_id, term, session))

            if cursor.fetchone():
                overwrite_warnings.append(name.strip())

        return render_template(
            "results_preview.html",
            df=df.to_dict(orient='records'),
            report_type=report_type,
            subject=subject,
            class_data=class_data,
            subject_id=subject_id,    
            class_arm_id=class_arm_id,
            term=term,
            session=session,
            temp_path=temp_path,
            overwrite_warnings=overwrite_warnings
        )

    except Exception as e:
        return render_template("error.html", message=str(e))

@uploads_bp.route('/confirm-results-upload', methods=['POST'])
def confirm_results_upload():
    """Final commit of results (after preview)."""
    report_type = request.form.get("report_type")
    subject_id = request.form.get("subject_id")
    class_arm_id = request.form.get("class_arm_id")
    term = request.form.get("term")
    session = request.form.get("session")
    temp_path = request.form.get("temp_path")

    if not os.path.exists(temp_path):
        return render_template("error.html", message="Temporary file missing. Please re-upload.")

    if report_type not in ("half_term", "full_term"):
        return render_template("error.html", message="Invalid report type.")

    # Call correct processing function
    if report_type == "half_term":
        errors, success_count = process_half_term_upload(temp_path, subject_id, class_arm_id, term, session)
    else:
        errors, success_count = process_full_term_upload(temp_path, subject_id, class_arm_id, term, session)

    # Cleanup
    os.remove(temp_path)

    if errors:
        return render_template("upload_error.html", errors=errors, success_count=success_count)

    return render_template("upload_success.html",
                           message=f"{success_count} records uploaded!",
                           success_count=success_count)

