# app.py - complete application (uses kembos_college.db and WeasyPrint)
import os
import sqlite3
import zipfile
from io import BytesIO
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, g,
    send_file, send_from_directory, flash
)
from werkzeug.utils import secure_filename
import pandas as pd
from weasyprint import HTML

# -------------------------
# Config
# -------------------------
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join("static", "uploads")
app.config['PHOTO_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], "photos")
app.config['ALLOWED_DATA_EXTENSIONS'] = {'csv', 'xlsx'}
app.config['ALLOWED_PHOTO_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'gif'}
app.config['DATABASE'] = 'kembos_college.db'
app.config['SECRET_KEY'] = 'change_this_secret_in_prod'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PHOTO_FOLDER'], exist_ok=True)


# -------------------------
# DB helpers
# -------------------------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# -------------------------
# Utilities
# -------------------------
def allowed_data_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_DATA_EXTENSIONS']

def allowed_photo_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_PHOTO_EXTENSIONS']

def get_current_session():
    now = datetime.now()
    if now.month >= 9:
        return f"{now.year}/{now.year + 1}"
    else:
        return f"{now.year - 1}/{now.year}"

def get_current_term():
    m = datetime.now().month
    if m in (1,2,3,4):
        return 3
    if m in (5,6,7,8):
        return 2
    return 1

def session_to_short(session_str):
    parts = session_str.split('/')
    if len(parts) == 2 and len(parts[0])>=2 and len(parts[1])>=2:
        return parts[0][-2:] + parts[1][-2:]
    return session_str.replace('/', '')[:4]

def generate_reg_number(class_name, session, term, index):
    class_abbr = class_name.replace(" ", "")
    session_short = session_to_short(session)
    return f"{class_abbr}-{session_short}-{term}-{index:03d}"

def get_next_reg_index(class_name, session, term):
    db = get_db()
    cursor = db.cursor()
    class_abbr = class_name.replace(" ", "")
    session_short = session_to_short(session)
    like_pattern = f"{class_abbr}-{session_short}-{term}-%"
    cursor.execute("SELECT reg_number FROM students WHERE reg_number LIKE ?", (like_pattern,))
    rows = cursor.fetchall()
    max_idx = 0
    for r in rows:
        rn = r['reg_number']
        try:
            serial = rn.split('-')[-1]
            idx = int(serial)
            if idx > max_idx:
                max_idx = idx
        except Exception:
            continue
    return max_idx + 1


# -------------------------
# Initialization / Schema
# -------------------------
def init_db():
    db = get_db()
    c = db.cursor()

    # base tables
    c.execute('''CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        level TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS class_arms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        arm TEXT NOT NULL,
        UNIQUE(class_id, arm),
        FOREIGN KEY(class_id) REFERENCES classes(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        level TEXT NOT NULL,
        description TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        level TEXT NOT NULL CHECK(level IN ('junior','senior')),
        is_common_core INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS department_subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        is_compulsory INTEGER DEFAULT 1,
        UNIQUE(department_id, subject_id),
        FOREIGN KEY(department_id) REFERENCES departments(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS class_subject_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_arm_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        is_compulsory INTEGER DEFAULT 1,
        UNIQUE(class_arm_id, subject_id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reg_number TEXT UNIQUE,
        full_name TEXT NOT NULL,
        age INTEGER,
        gender TEXT,
        photo TEXT,
        department_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(department_id) REFERENCES departments(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS student_classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        class_arm_id INTEGER NOT NULL,
        session TEXT NOT NULL,
        term INTEGER NOT NULL,
        UNIQUE(student_id, class_arm_id, session, term),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        class_arm_id INTEGER NOT NULL,
        term INTEGER NOT NULL,
        session TEXT NOT NULL,
        ca1_score REAL DEFAULT 0,
        ca2_score REAL DEFAULT 0,
        ca3_score REAL DEFAULT 0,
        ca4_score REAL DEFAULT 0,
        exam_score REAL DEFAULT 0,
        total_score REAL DEFAULT 0,
        report_type TEXT NOT NULL CHECK(report_type IN ('half_term', 'full_term')),
        UNIQUE(student_id, subject_id, class_arm_id, term, session, report_type),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        class_arm_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        status TEXT CHECK(status IN ('present','absent','late')),
        term INTEGER NOT NULL,
        session TEXT NOT NULL,
        year INTEGER,
        UNIQUE(student_id, class_arm_id, date),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS attendance_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        class_arm_id INTEGER NOT NULL,
        term INTEGER NOT NULL,
        session TEXT NOT NULL,
        days_present INTEGER DEFAULT 0,
        days_absent INTEGER DEFAULT 0,
        days_late INTEGER DEFAULT 0,
        total_school_days INTEGER DEFAULT 0,
        UNIQUE(student_id, class_arm_id, term, session),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS student_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        class_arm_id INTEGER NOT NULL,
        term INTEGER NOT NULL,
        session TEXT NOT NULL,
        handwriting INTEGER CHECK(handwriting BETWEEN 1 AND 5),
        sports_participation INTEGER CHECK(sports_participation BETWEEN 1 AND 5),
        practical_skills INTEGER CHECK(practical_skills BETWEEN 1 AND 5),
        punctuality INTEGER CHECK(punctuality BETWEEN 1 AND 5),
        politeness INTEGER CHECK(politeness BETWEEN 1 AND 5),
        neatness INTEGER CHECK(neatness BETWEEN 1 AND 5),
        class_teacher_comment TEXT,
        principal_comment TEXT,
        UNIQUE(student_id, class_arm_id, term, session),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(class_arm_id) REFERENCES class_arms(id)
    )''')

    db.commit()

    # seed minimal classes, arms, departments, subjects if absent
    seed_data()

def seed_data():
    db = get_db()
    c = db.cursor()

    base_classes = [
        ("JSS 1", "JSS"),
        ("JSS 2", "JSS"),
        ("JSS 3", "JSS"),
        ("SSS 1", "SSS"),
        ("SSS 2", "SSS"),
        ("SSS 3", "SSS"),
    ]
    for name, level in base_classes:
        c.execute("INSERT OR IGNORE INTO classes (name, level) VALUES (?, ?)", (name, level))
    db.commit()

    # Ensure class arms (GENERAL, GOLD, DIAMOND)
    c.execute("SELECT id FROM classes")
    for r in c.fetchall():
        cid = r['id']
        for arm in ("GENERAL", "GOLD", "DIAMOND"):
            c.execute("INSERT OR IGNORE INTO class_arms (class_id, arm) VALUES (?, ?)", (cid, arm))
    db.commit()

    # departments
    departments = [
        ("Junior General", "junior", "Junior general subjects"),
        ("Science", "senior", "Science department"),
        ("Arts/Humanities", "senior", "Arts and Humanities"),
        ("Commercial", "senior", "Commercial/Business"),
    ]
    for name, level, desc in departments:
        c.execute("INSERT OR IGNORE INTO departments (name, level, description) VALUES (?, ?, ?)", (name, level, desc))
    db.commit()

    # subjects (small set)
    subj_list = [
        ("Mathematics", "junior", 1),
        ("English", "junior", 1),
        ("Basic Science", "junior", 0),
        ("Civic Education", "junior", 1),
        ("Mathematics", "senior", 1),
        ("English", "senior", 1),
        ("Physics", "senior", 0),
        ("Chemistry", "senior", 0),
        ("Biology", "senior", 0),
        ("Literature in English", "senior", 0),
        ("Economics", "senior", 0),
    ]
    for name, level, is_core in subj_list:
        c.execute("INSERT OR IGNORE INTO subjects (name, level, is_common_core) VALUES (?, ?, ?)", (name, level, is_core))
    db.commit()

    # department_subjects mapping (idempotent insertion)
    # simplified mapping for seed (you can extend)
    c.execute("SELECT id, name FROM departments")
    depts = {r['name']: r['id'] for r in c.fetchall()}
    c.execute("SELECT id, name, level FROM subjects")
    subs = {f"{r['name']}_{r['level']}": r['id'] for r in c.fetchall()}

    # junior dept -> all junior subjects compulsory
    if "Junior General" in depts:
        jd = depts["Junior General"]
        for key, sid in subs.items():
            if key.endswith("_junior"):
                c.execute("INSERT OR IGNORE INTO department_subjects (department_id, subject_id, is_compulsory) VALUES (?, ?, ?)", (jd, sid, 1))
    db.commit()

    # basic class_subject_requirements: junior all junior subjects; senior common core
    c.execute("SELECT ca.id as arm_id, c.name as class_name, c.level FROM class_arms ca JOIN classes c ON ca.class_id = c.id")
    for ca in c.fetchall():
        arm_id = ca['arm_id']
        level = ca['level']
        if level == 'JSS':
            c.execute("INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory) SELECT ?, id, 1 FROM subjects WHERE level = 'junior'", (arm_id,))
        else:
            c.execute("INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory) SELECT ?, id, 1 FROM subjects WHERE level = 'senior' AND is_common_core = 1", (arm_id,))
    db.commit()


# -------------------------
# Basic pages & students
# -------------------------
@app.route('/')
def home():
    classes = get_class_status()
    return render_template('home.html', classes=classes, current_session=get_current_session(), current_term=get_current_term())

@app.route('/students')
def view_students():
    db = get_db()
    c = db.cursor()
    class_filter = request.args.get('class_filter', 'all')
    session_filter = request.args.get('session', get_current_session())
    term_filter = request.args.get('term', get_current_term())

    c.execute("""SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm""")
    class_arms = c.fetchall()

    if class_filter == 'all':
        c.execute("""SELECT s.id, s.reg_number, s.full_name, s.age, s.photo, c.name || ' ' || a.arm AS class_name, sc.session, sc.term
                     FROM students s
                     JOIN student_classes sc ON s.id = sc.student_id
                     JOIN class_arms a ON sc.class_arm_id = a.id
                     JOIN classes c ON a.class_id = c.id
                     WHERE sc.session = ?
                     ORDER BY c.name, a.arm, s.full_name""", (session_filter,))
        students = c.fetchall()
    else:
        c.execute("""SELECT s.id, s.reg_number, s.full_name, s.age, s.photo, c.name || ' ' || a.arm AS class_name, sc.session, sc.term
                     FROM students s
                     JOIN student_classes sc ON s.id = sc.student_id
                     JOIN class_arms a ON sc.class_arm_id = a.id
                     JOIN classes c ON a.class_id = c.id
                     WHERE sc.session = ? AND sc.class_arm_id = ?
                     ORDER BY s.full_name""", (session_filter, class_filter))
        students = c.fetchall()

    return render_template('students.html', students=students, classes=class_arms, selected_class=class_filter, selected_session=session_filter, selected_term=term_filter)


@app.route('/upload-students', methods=['GET', 'POST'])
def upload_students():
    db = get_db()
    c = db.cursor()
    if request.method == 'GET':
        c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
        classes = c.fetchall()
        return render_template('upload_students.html', classes=classes, current_session=get_current_session(), current_term=get_current_term())

    # POST handling
    class_arm_id = request.form.get('class_arm_id')
    session = request.form.get('session', get_current_session())
    term = int(request.form.get('term', get_current_term()))
    if 'file' not in request.files:
        flash("No file provided", "error")
        return redirect(url_for('upload_students'))
    file = request.files['file']
    if file.filename == '':
        flash("Empty filename", "error")
        return redirect(url_for('upload_students'))
    if not allowed_data_file(file.filename):
        flash("Invalid file type", "error")
        return redirect(url_for('upload_students'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    errors, success_count = process_student_upload(filepath, class_arm_id, session, term)
    if errors:
        return render_template('upload_error.html', errors=errors, success_count=success_count)
    return render_template('upload_success.html', success_count=success_count, message=f"{success_count} students created")


# Photo upload / management
@app.route('/upload-photo/<reg_number>', methods=['GET', 'POST'])
def upload_photo(reg_number):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT * FROM students WHERE reg_number = ?", (reg_number,))
    student = c.fetchone()
    if not student:
        return render_template('error.html', message="Student not found")

    if request.method == 'GET':
        return render_template('upload_photo.html', student=student)

    # POST - file upload
    if 'photo' not in request.files:
        return render_template('upload_error.html', errors=["No file selected"])
    file = request.files['photo']
    if file.filename == '':
        return render_template('upload_error.html', errors=["Empty filename"])
    if not allowed_photo_file(file.filename):
        return render_template('upload_error.html', errors=["Invalid image type"])

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f"{reg_number}.{ext}")
    out_path = os.path.join(app.config['PHOTO_FOLDER'], filename)
    file.save(out_path)
    c.execute("UPDATE students SET photo = ? WHERE reg_number = ?", (filename, reg_number))
    db.commit()
    return redirect(url_for('view_students'))


@app.route('/uploads/photos/<filename>')
def serve_photo(filename):
    return send_from_directory(app.config['PHOTO_FOLDER'], filename)


# -------------------------
# Student processing (used in upload_students)
# -------------------------
def process_student_upload(filepath, class_arm_id, session, term):
    errors = []
    success_count = 0
    db = get_db()
    c = db.cursor()

    try:
        if filepath.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        if 'full_name' not in df.columns:
            return (["Missing required column: full_name"], 0)

        # fetch class info
        c.execute("SELECT c.name AS class_name, c.level FROM class_arms a JOIN classes c ON a.class_id = c.id WHERE a.id = ?", (class_arm_id,))
        class_info = c.fetchone()
        if not class_info:
            return (["Invalid class_arm selected"], 0)
        class_name = class_info['class_name']
        class_level = class_info['level']

        # existing names in this class/session/term to avoid duplicates
        c.execute("""SELECT LOWER(TRIM(s.full_name)) as ln FROM students s
                     JOIN student_classes sc ON s.id = sc.student_id
                     WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ?""", (class_arm_id, session, term))
        existing = {r['ln'] for r in c.fetchall()}

        processed = set()
        new_students = []

        for _, row in df.iterrows():
            full_name = str(row.get('full_name', '')).strip()
            if not full_name:
                continue
            ln = full_name.lower()
            if ln in processed:
                errors.append(f"Duplicate in file skipped: {full_name}")
                continue
            processed.add(ln)
            if ln in existing:
                errors.append(f"Already exists in class/session/term: {full_name}")
                continue
            age = int(row['age']) if 'age' in row and pd.notna(row['age']) else None
            gender = str(row['gender']).strip() if 'gender' in row and pd.notna(row['gender']) else None
            dept_name = str(row['department']).strip() if 'department' in row and pd.notna(row['department']) else None
            new_students.append({'full_name': full_name, 'age': age, 'gender': gender, 'department': dept_name})

        if not new_students:
            return (errors or ["No new students to add"], 0)

        # department lookup
        c.execute("SELECT id, name FROM departments")
        depts = {r['name'].lower(): r['id'] for r in c.fetchall()}

        start_index = get_next_reg_index(class_name, session, term)
        idx = start_index

        for sdata in new_students:
            try:
                reg = generate_reg_number(class_name, session, term, idx)
                idx += 1
                dept_id = None
                if class_level == 'JSS':
                    c.execute("SELECT id FROM departments WHERE name = 'Junior General'")
                    rr = c.fetchone()
                    dept_id = rr['id'] if rr else None
                else:
                    if sdata['department'] and sdata['department'].lower() in depts:
                        dept_id = depts[sdata['department'].lower()]
                    else:
                        # default to Science for SSS
                        c.execute("SELECT id FROM departments WHERE name = 'Science'")
                        rr = c.fetchone()
                        dept_id = rr['id'] if rr else None

                c.execute("INSERT OR IGNORE INTO students (reg_number, full_name, age, gender, department_id) VALUES (?, ?, ?, ?, ?)",
                          (reg, sdata['full_name'], sdata['age'], sdata['gender'], dept_id))
                student_row = c.execute("SELECT id FROM students WHERE reg_number = ?", (reg,)).fetchone()
                if student_row:
                    c.execute("INSERT OR IGNORE INTO student_classes (student_id, class_arm_id, session, term) VALUES (?, ?, ?, ?)",
                              (student_row['id'], class_arm_id, session, term))
                    success_count += 1
            except Exception as e:
                errors.append(f"Error creating {sdata['full_name']}: {e}")

        db.commit()
    except Exception as e:
        errors.append(f"File processing error: {e}")

    return errors, success_count


# -------------------------
# Results upload (half & full)
# -------------------------
@app.route('/upload-half-term-results', methods=['GET'])
def upload_half_term_results():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT * FROM subjects ORDER BY name")
    subjects = c.fetchall()
    c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
    classes = c.fetchall()
    return render_template('upload_half_term_results.html', subjects=subjects, classes=classes, current_session=get_current_session())

@app.route('/process-half-term-results', methods=['POST'])
def process_half_term_results():
    subject_id = int(request.form['subject_id'])
    class_arm_id = int(request.form['class_arm_id'])
    term = int(request.form['term'])
    session = request.form['session']
    if 'file' not in request.files:
        flash("No file provided", "error")
        return redirect(url_for('upload_half_term_results'))
    file = request.files['file']
    if file.filename == '' or not allowed_data_file(file.filename):
        flash("Invalid file", "error")
        return redirect(url_for('upload_half_term_results'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
    file.save(filepath)
    errors, success = process_half_term_upload(filepath, subject_id, class_arm_id, term, session)
    if errors:
        return render_template('upload_error.html', errors=errors, success_count=success)
    return render_template('upload_success.html', success_count=success, message=f"{success} half-term scores uploaded")

def process_half_term_upload(filepath, subject_id, class_arm_id, term, session):
    errors = []
    success = 0
    db = get_db()
    c = db.cursor()
    try:
        if filepath.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        req = {'full_name','ca1_score','ca2_score'}
        missing = req - set(df.columns)
        if missing:
            return [f"Missing columns: {', '.join(missing)}"], 0
        for _, row in df.iterrows():
            name = str(row['full_name']).strip()
            ca1 = float(row['ca1_score']) if pd.notna(row['ca1_score']) else 0
            ca2 = float(row['ca2_score']) if pd.notna(row['ca2_score']) else 0
            if not (0 <= ca1 <= 5) or not (0 <= ca2 <= 5):
                errors.append(f"Invalid CA score for {name}")
                continue
            total = ca1 + ca2
            c.execute("""SELECT s.id FROM students s JOIN student_classes sc ON s.id = sc.student_id
                         WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ? AND LOWER(s.full_name) = LOWER(?)""",
                      (class_arm_id, session, term, name.lower()))
            student = c.fetchone()
            if not student:
                errors.append(f"Student not found in class: {name}")
                continue
            student_id = student['id']
            c.execute("""INSERT OR REPLACE INTO scores (student_id, subject_id, class_arm_id, term, session,
                         ca1_score, ca2_score, total_score, report_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (student_id, subject_id, class_arm_id, term, session, ca1, ca2, total, 'half_term'))
            success += 1
        db.commit()
    except Exception as e:
        errors.append(str(e))
    return errors, success


@app.route('/upload-full-term-results', methods=['GET'])
def upload_full_term_results():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT * FROM subjects ORDER BY name")
    subjects = c.fetchall()
    c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
    classes = c.fetchall()
    return render_template('upload_full_term_results.html', subjects=subjects, classes=classes, current_session=get_current_session())

@app.route('/process-full-term-results', methods=['POST'])
def process_full_term_results():
    subject_id = int(request.form['subject_id'])
    class_arm_id = int(request.form['class_arm_id'])
    term = int(request.form['term'])
    session = request.form['session']
    if 'file' not in request.files:
        flash("No file", "error")
        return redirect(url_for('upload_full_term_results'))
    file = request.files['file']
    if file.filename == '' or not allowed_data_file(file.filename):
        flash("Invalid file", "error")
        return redirect(url_for('upload_full_term_results'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
    file.save(filepath)
    errors, success = process_full_term_upload(filepath, subject_id, class_arm_id, term, session)
    if errors:
        return render_template('upload_error.html', errors=errors, success_count=success)
    return render_template('upload_success.html', success_count=success, message=f"{success} full-term scores uploaded")

def process_full_term_upload(filepath, subject_id, class_arm_id, term, session):
    errors = []
    success = 0
    db = get_db()
    c = db.cursor()
    try:
        if filepath.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        req = {'full_name','ca1_score','ca2_score','ca3_score','ca4_score','exam_score'}
        missing = req - set(df.columns)
        if missing:
            return [f"Missing columns: {', '.join(missing)}"], 0
        for _, row in df.iterrows():
            name = str(row['full_name']).strip()
            ca1 = float(row['ca1_score']) if pd.notna(row['ca1_score']) else 0
            ca2 = float(row['ca2_score']) if pd.notna(row['ca2_score']) else 0
            ca3 = float(row['ca3_score']) if pd.notna(row['ca3_score']) else 0
            ca4 = float(row['ca4_score']) if pd.notna(row['ca4_score']) else 0
            exam = float(row['exam_score']) if pd.notna(row['exam_score']) else 0
            # validate ranges
            bad = False
            for v, mx, label in ((ca1,5,'CA1'),(ca2,5,'CA2'),(ca3,5,'CA3'),(ca4,5,'CA4')):
                if not (0 <= v <= mx):
                    errors.append(f"{label} out of range for {name}")
                    bad = True
            if not (0 <= exam <= 80):
                errors.append(f"Exam out of range for {name}")
                bad = True
            if bad:
                continue
            total = ca1 + ca2 + ca3 + ca4 + exam
            c.execute("""SELECT s.id FROM students s JOIN student_classes sc ON s.id = sc.student_id
                         WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ? AND LOWER(s.full_name) = LOWER(?)""",
                      (class_arm_id, session, term, name.lower()))
            student = c.fetchone()
            if not student:
                errors.append(f"Student not found in class: {name}")
                continue
            student_id = student['id']
            c.execute("""INSERT OR REPLACE INTO scores (student_id, subject_id, class_arm_id, term, session,
                         ca1_score, ca2_score, ca3_score, ca4_score, exam_score, total_score, report_type)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (student_id, subject_id, class_arm_id, term, session, ca1, ca2, ca3, ca4, exam, total, 'full_term'))
            success += 1
        db.commit()
    except Exception as e:
        errors.append(str(e))
    return errors, success


# -------------------------
# View results
# -------------------------
@app.route('/results')
def view_results():
    db = get_db()
    c = db.cursor()
    c.execute('''SELECT s.reg_number, s.full_name, c.name || ' ' || ca.arm AS class_name,
                        sub.name AS subject, sc.total_score AS score, sc.term, sc.session
                 FROM scores sc
                 JOIN students s ON sc.student_id = s.id
                 JOIN subjects sub ON sc.subject_id = sub.id
                 JOIN class_arms ca ON sc.class_arm_id = ca.id
                 JOIN classes c ON ca.class_id = c.id
                 ORDER BY sc.session DESC, sc.term DESC, c.name, ca.arm, s.full_name''')
    results = c.fetchall()
    return render_template('results.html', results=results)


# -------------------------
# Report generation (WeasyPrint)
# -------------------------
@app.route('/generate-reports', methods=['GET', 'POST'])
def generate_reports():
    db = get_db()
    c = db.cursor()
    if request.method == 'GET':
        c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
        classes = c.fetchall()
        return render_template('report_form.html', classes=classes, current_session=get_current_session(), current_term=get_current_term())

    # POST -> generate
    full_name = request.form.get('full_name', '').strip()
    class_arm_id = int(request.form['class_arm_id'])
    term = int(request.form['term'])
    session = request.form['session']
    report_type = request.form.get('report_type', 'full_term')

    # single student (by name + class_arm_id + term + session)
    if full_name:
        c.execute("""SELECT s.*, c.name || ' ' || a.arm AS class_name
                     FROM students s
                     JOIN student_classes sc ON s.id = sc.student_id
                     JOIN class_arms a ON sc.class_arm_id = a.id
                     JOIN classes c ON a.class_id = c.id
                     WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ? AND LOWER(s.full_name) = LOWER(?)""",
                  (class_arm_id, session, term, full_name.lower()))
        student = c.fetchone()
        if not student:
            return render_template('error.html', message="Student not found")
        c.execute("""SELECT sub.name AS subject, sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score, sc.exam_score, sc.total_score, sc.report_type
                     FROM scores sc JOIN subjects sub ON sc.subject_id = sub.id
                     WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ? AND sc.report_type = ?""",
                  (student['id'], term, session, report_type))
        scores = c.fetchall()
        if not scores:
            return render_template('error.html', message="No results found for this student")
        # attendance summary
        c.execute("SELECT days_present, days_absent, days_late, total_school_days FROM attendance_summary WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?",
                  (student['id'], class_arm_id, term, session))
        attendance_summary = c.fetchone()
        total = sum(r['total_score'] for r in scores)
        average = (total / len(scores)) if scores else 0
        # Render HTML report (template should match keys)
        html = render_template('student_report.html',
                               student=student,
                               class_name=student['class_name'],
                               scores=scores,
                               term=term,
                               session=session,
                               average=average,
                               attendance_summary=attendance_summary,
                               current_date=datetime.now().strftime('%Y-%m-%d'))
        # optionally deliver as PDF (query param ?format=pdf)
        if request.form.get('output') == 'pdf' or request.args.get('format') == 'pdf':
            pdf_filename = f"{secure_filename(student['full_name'])}_report.pdf"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
            HTML(string=html, base_url=request.root_path).write_pdf(pdf_path)
            return send_file(pdf_path, as_attachment=True)
        return html

    # batch: whole class -> build per-student PDFs and zip
    c.execute("""SELECT s.id, s.reg_number, s.full_name, s.age, s.photo, c.name || ' ' || a.arm AS class_name
                 FROM students s
                 JOIN student_classes sc ON s.id = sc.student_id
                 JOIN class_arms a ON sc.class_arm_id = a.id
                 JOIN classes c ON a.class_id = c.id
                 WHERE sc.class_arm_id = ? AND sc.session = ?
                 ORDER BY s.full_name""", (class_arm_id, session))
    students = c.fetchall()
    if not students:
        return render_template('error.html', message="No students found for this class/session")

    zip_name = f"class_{class_arm_id}_term{term}_{session.replace('/','')}_reports.zip"
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_name)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for st in students:
            c.execute("""SELECT sub.name AS subject, sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score, sc.exam_score, sc.total_score, sc.report_type
                         FROM scores sc JOIN subjects sub ON sc.subject_id = sub.id
                         WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ?""",
                      (st['id'], term, session))
            scores = c.fetchall()
            if not scores:
                continue
            total = sum(r['total_score'] for r in scores)
            average = (total / len(scores)) if scores else 0
            html = render_template('student_report.html',
                                   student=st,
                                   class_name=st['class_name'],
                                   scores=scores,
                                   term=term,
                                   session=session,
                                   average=average,
                                   current_date=datetime.now().strftime('%Y-%m-%d'))
            pdf_file = f"{secure_filename(st['full_name'])}_report.pdf"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file)
            HTML(string=html, base_url=request.root_path).write_pdf(pdf_path)
            zf.write(pdf_path, pdf_file)
            os.remove(pdf_path)
    return send_file(zip_path, as_attachment=True)


# -------------------------
# student-report route (supports reg_number or name/class)
# -------------------------
@app.route('/student-report', methods=['GET'])
def student_report():
    db = get_db()
    c = db.cursor()
    # Option A: by reg_number
    reg_number = request.args.get('reg_number')
    if reg_number:
        c.execute("SELECT * FROM students WHERE reg_number = ?", (reg_number,))
        student = c.fetchone()
        if not student:
            return render_template('error.html', message="Student not found")
        # find student's current class assignment (latest session)
        c.execute("""SELECT sc.class_arm_id, c.name || ' ' || a.arm AS class_name
                     FROM student_classes sc JOIN class_arms a ON sc.class_arm_id = a.id JOIN classes c ON a.class_id = c.id
                     WHERE sc.student_id = ? ORDER BY sc.session DESC LIMIT 1""", (student['id'],))
        class_info = c.fetchone()
        class_arm_id = class_info['class_arm_id'] if class_info else None
        class_name = class_info['class_name'] if class_info else "Unknown"
        # term/session parameters
        term = int(request.args.get('term', get_current_term()))
        session = request.args.get('session', get_current_session())
        report_type = request.args.get('report_type', 'full_term')
        c.execute("""SELECT sub.name AS subject, sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score, sc.exam_score, sc.total_score, sc.report_type
                     FROM scores sc JOIN subjects sub ON sc.subject_id = sub.id
                     WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ? AND sc.report_type = ?""",
                  (student['id'], term, session, report_type))
        scores = c.fetchall()
        if not scores:
            return render_template('error.html', message="No results found")
        c.execute("SELECT days_present, days_absent, days_late, total_school_days FROM attendance_summary WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?",
                  (student['id'], class_arm_id, term, session))
        attendance_summary = c.fetchone()
        average = sum(r['total_score'] for r in scores) / len(scores) if scores else 0
        return render_template('student_report.html', student=student, class_name=class_name, scores=scores,
                               term=term, session=session, average=average, attendance_summary=attendance_summary, current_date=datetime.now().strftime('%Y-%m-%d'))

    # Option B: by full_name + class_arm_id + term + session
    full_name = request.args.get('full_name')
    class_arm_id = request.args.get('class_arm_id')
    term = request.args.get('term', type=int)
    session = request.args.get('session')
    if full_name and class_arm_id and term and session:
        c.execute("""SELECT s.*, c.name || ' ' || a.arm AS class_name
                     FROM students s
                     JOIN student_classes sc ON s.id = sc.student_id
                     JOIN class_arms a ON sc.class_arm_id = a.id
                     JOIN classes c ON a.class_id = c.id
                     WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ? AND LOWER(s.full_name) = LOWER(?)""",
                  (class_arm_id, session, term, full_name.strip().lower()))
        student = c.fetchone()
        if not student:
            return render_template('error.html', message="Student not found")
        c.execute("""SELECT sub.name AS subject, sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score, sc.exam_score, sc.total_score, sc.report_type
                     FROM scores sc JOIN subjects sub ON sc.subject_id = sub.id
                     WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ?""",
                  (student['id'], term, session))
        scores = c.fetchall()
        if not scores:
            return render_template('error.html', message="No results")
        c.execute("SELECT days_present, days_absent, days_late, total_school_days FROM attendance_summary WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?",
                  (student['id'], class_arm_id, term, session))
        attendance_summary = c.fetchone()
        average = sum(r['total_score'] for r in scores) / len(scores) if scores else 0
        return render_template('student_report.html', student=student, class_name=student['class_name'], scores=scores,
                               term=term, session=session, average=average, attendance_summary=attendance_summary, current_date=datetime.now().strftime('%Y-%m-%d'))

    # fallback: show report form
    c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
    classes = c.fetchall()
    return render_template('report_form.html', classes=classes, current_session=get_current_session())


# -------------------------
# Attendance routes
# -------------------------
@app.route('/attendance/sheet/<int:class_arm_id>', methods=['GET'])
@app.route('/attendance/sheet/<int:class_arm_id>/<date>/<int:term>', methods=['GET'])
def attendance_sheet(class_arm_id, date=None, term=None):
    db = get_db()
    c = db.cursor()
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    if term is None:
        term = get_current_term()
    session = get_current_session()
    c.execute("SELECT c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id WHERE a.id = ?", (class_arm_id,))
    class_info = c.fetchone()
    if not class_info:
        return redirect(url_for('home'))
    c.execute("""SELECT s.id, s.reg_number, s.full_name, s.photo FROM students s
                 JOIN student_classes sc ON s.id = sc.student_id
                 WHERE sc.class_arm_id = ? AND sc.session = ? ORDER BY s.full_name""", (class_arm_id, session))
    students = c.fetchall()
    c.execute("SELECT student_id, status FROM attendance WHERE class_arm_id = ? AND date = ? AND term = ? AND session = ?", (class_arm_id, date, term, session))
    existing = {r['student_id']: r['status'] for r in c.fetchall()}
    return render_template('attendance_sheet.html', class_info=class_info, students=students, date=date, term=term, session=session, existing=existing, class_arm_id=class_arm_id)

@app.route('/attendance/submit', methods=['POST'])
def attendance_submit():
    db = get_db()
    c = db.cursor()
    class_arm_id = int(request.form['class_arm_id'])
    date = request.form['date']
    term = int(request.form['term'])
    session = request.form.get('session', get_current_session())
    # remove existing for that date
    # but we will replace per student based on posted fields
    for key, value in request.form.items():
        if key.startswith('status_'):
            student_id = int(key.split('_',1)[1])
            c.execute("DELETE FROM attendance WHERE student_id = ? AND class_arm_id = ? AND date = ?", (student_id, class_arm_id, date))
            if value in ('present','absent','late'):
                c.execute("INSERT INTO attendance (student_id, class_arm_id, date, status, term, session, year) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (student_id, class_arm_id, date, value, term, session, datetime.now().year))
    db.commit()
    return redirect(url_for('class_teacher_portal'))


@app.route('/attendance/summary/<int:class_arm_id>/<int:term>/<path:session>')
def attendance_summary(class_arm_id, term, session):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT c.name as class_name, a.arm FROM class_arms a JOIN classes c ON a.class_id = c.id WHERE a.id = ?", (class_arm_id,))
    class_info = c.fetchone()
    c.execute("""SELECT s.id, s.reg_number, s.full_name, s.photo FROM students s
                 JOIN student_classes sc ON s.id = sc.student_id
                 WHERE sc.class_arm_id = ? AND sc.session = ? ORDER BY s.full_name""", (class_arm_id, session))
    students = c.fetchall()
    attendance_data = {}
    total_school_days = None
    for s in students:
        c.execute("SELECT days_present, days_absent, days_late, total_school_days FROM attendance_summary WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?", (s['id'], class_arm_id, term, session))
        row = c.fetchone()
        if row:
            attendance_data[s['id']] = row
            if total_school_days is None:
                total_school_days = row['total_school_days']
    return render_template('attendance_summary.j2', class_info=class_info, students=students, attendance_data=attendance_data, total_school_days=total_school_days, class_arm_id=class_arm_id, term=term, session=session)


@app.route('/attendance/submit-summary', methods=['POST'])
def attendance_submit_summary():
    class_arm_id = int(request.form['class_arm_id'])
    term = int(request.form['term'])
    session = request.form['session']
    total_school_days = int(request.form['total_school_days'])
    db = get_db()
    c = db.cursor()
    c.execute("SELECT s.id FROM students s JOIN student_classes sc ON s.id = sc.student_id WHERE sc.class_arm_id = ? AND sc.session = ?", (class_arm_id, session))
    students = c.fetchall()
    for s in students:
        sid = s['id']
        present = int(request.form.get(f'present_{sid}', 0))
        absent = int(request.form.get(f'absent_{sid}', 0))
        late = int(request.form.get(f'late_{sid}', 0))
        c.execute("""INSERT OR REPLACE INTO attendance_summary (student_id, class_arm_id, term, session, days_present, days_absent, days_late, total_school_days)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (sid, class_arm_id, term, session, present, absent, late, total_school_days))
    db.commit()
    return redirect(url_for('class_teacher_class_view', class_arm_id=class_arm_id, session=session, term=term))


# -------------------------
# Class teacher portal & views
# -------------------------
@app.route('/class-teacher')
def class_teacher_portal():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT a.id as arm_id, c.name as class_name, a.arm, c.level FROM class_arms a JOIN classes c ON a.class_id = c.id ORDER BY c.id, a.arm")
    classes = c.fetchall()
    return render_template('class_teacher_portal.html', classes=classes, current_session=get_current_session(), current_term=get_current_term())


@app.route('/class-teacher/class/<int:class_arm_id>/<path:session>/<int:term>')
def class_teacher_class_view(class_arm_id, session, term):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT c.name as class_name, a.arm, c.level FROM class_arms a JOIN classes c ON a.class_id = c.id WHERE a.id = ?", (class_arm_id,))
    class_info = c.fetchone()
    c.execute("""SELECT s.id, s.reg_number, s.full_name, s.age, s.gender, s.photo, s.department_id, d.name AS department_name
                 FROM students s JOIN student_classes sc ON s.id = sc.student_id
                 LEFT JOIN departments d ON s.department_id = d.id
                 WHERE sc.class_arm_id = ? AND sc.session = ? ORDER BY s.full_name""", (class_arm_id, session))
    students = c.fetchall()
    assessment_data = {}
    for st in students:
        c.execute("SELECT * FROM student_assessments WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?", (st['id'], class_arm_id, term, session))
        assessment_data[st['id']] = c.fetchone()
    half_status = []  # reuse get_upload_status if desired
    full_status = []  # reuse get_upload_status if desired
    return render_template('class_teacher_class_view.html', class_info=class_info, students=students, assessment_data=assessment_data, class_arm_id=class_arm_id, session=session, term=term, current_date=datetime.now().strftime('%Y-%m-%d'))


# -------------------------
# Subjects & Departments management (basic)
# -------------------------
@app.route('/subjects')
def subjects():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT * FROM subjects ORDER BY name")
    subs = c.fetchall()
    return render_template('subjects.html', subjects=subs)

@app.route('/add-subject', methods=['POST'])
def add_subject():
    name = request.form['name'].strip()
    level = request.form['level']
    is_core = int(request.form.get('is_common_core', 0))
    c = get_db().cursor()
    c.execute("INSERT OR IGNORE INTO subjects (name, level, is_common_core) VALUES (?, ?, ?)", (name, level, is_core))
    get_db().commit()
    return redirect(url_for('subjects'))

@app.route('/departments')
def departments():
    c = get_db().cursor()
    c.execute("SELECT * FROM departments ORDER BY name")
    depts = c.fetchall()
    return render_template('departments.html', departments=depts)

@app.route('/add-department', methods=['POST'])
def add_department():
    name = request.form['name'].strip()
    level = request.form['level']
    desc = request.form.get('description', '')
    c = get_db().cursor()
    c.execute("INSERT OR IGNORE INTO departments (name, level, description) VALUES (?, ?, ?)", (name, level, desc))
    get_db().commit()
    return redirect(url_for('departments'))


# -------------------------
# Utilities used by templates
# -------------------------
def get_class_status():
    db = get_db()
    c = db.cursor()
    current_session = get_current_session()
    c.execute("""WITH cas AS (
                    SELECT sc.class_arm_id, COUNT(DISTINCT sc.student_id) AS cnt
                    FROM student_classes sc WHERE sc.session = ? GROUP BY sc.class_arm_id
                 )
                 SELECT ca.id AS arm_id, c.name AS class_name, ca.arm, COALESCE(cas.cnt, 0) AS student_count
                 FROM class_arms ca JOIN classes c ON ca.class_id = c.id
                 LEFT JOIN cas ON ca.id = cas.class_arm_id
                 ORDER BY c.id, ca.arm""", (current_session,))
    rows = c.fetchall()
    return rows


# -------------------------
# Startup
# -------------------------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
