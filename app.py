import os
import socket
import pandas as pd
from flask import Flask, render_template, request, redirect, abort, url_for, g, session, send_file, send_from_directory
from werkzeug.utils import secure_filename
from playwright.sync_api import sync_playwright
import sqlite3
import zipfile, tempfile
from io import BytesIO
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Protection
from datetime import datetime
from weasyprint import HTML

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}
app.config['DATABASE'] = 'school_results.db'
app.config['SECRET_KEY'] = 'school_result_secret_key'

# Create necessary directories
# os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], "photos"), exist_ok=True)


# Database helper functions
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

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Classes table
        cursor.execute('''CREATE TABLE IF NOT EXISTS classes (
                        id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        level TEXT NOT NULL)''')

        # Class arms table
        cursor.execute("""CREATE TABLE IF NOT EXISTS class_arms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_id INTEGER NOT NULL,
                    arm TEXT NOT NULL,
                    UNIQUE(class_id, arm),
                    FOREIGN KEY (class_id) REFERENCES classes (id))""")
    
        # Students table
        cursor.execute("""CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reg_number TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    age INTEGER,
                    gender TEXT,
                    photo TEXT,
                    department_id INTEGER,
                    FOREIGN KEY (department_id) REFERENCES departments (id))""")

        # Student → class assignment
        cursor.execute("""CREATE TABLE IF NOT EXISTS student_classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    class_arm_id INTEGER NOT NULL,
                    session TEXT NOT NULL,
                    term INTEGER NOT NULL,
                    UNIQUE(student_id, class_arm_id, session, term),
                    FOREIGN KEY (student_id) REFERENCES students (id),
                    FOREIGN KEY (class_arm_id) REFERENCES class_arms (id))""")

        # Subjects table
        cursor.execute("""CREATE TABLE IF NOT EXISTS subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    level TEXT NOT NULL CHECK(level IN ('junior', 'senior')),
                    is_common_core BOOLEAN DEFAULT 0)""")

        # Departments table
        cursor.execute("""CREATE TABLE IF NOT EXISTS departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    level TEXT NOT NULL CHECK(level IN ('junior', 'senior')),
                    description TEXT)""")

        # Department-Subject relationships
        cursor.execute("""CREATE TABLE IF NOT EXISTS department_subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    department_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    is_compulsory BOOLEAN DEFAULT 1,
                    UNIQUE(department_id, subject_id),
                    FOREIGN KEY (department_id) REFERENCES departments (id),
                    FOREIGN KEY (subject_id) REFERENCES subjects (id))""")

        # Class-Subject requirements
        cursor.execute("""CREATE TABLE IF NOT EXISTS class_subject_requirements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_arm_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    is_compulsory BOOLEAN DEFAULT 1,
                    UNIQUE(class_arm_id, subject_id),
                    FOREIGN KEY (class_arm_id) REFERENCES class_arms (id),
                    FOREIGN KEY (subject_id) REFERENCES subjects (id))""")

        # Scores table with report_type
        cursor.execute('''CREATE TABLE IF NOT EXISTS scores (
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
                        created_at TEXT NOT NULL,                       
                        UNIQUE(student_id, subject_id, class_arm_id, term, session, report_type),
                        FOREIGN KEY(student_id) REFERENCES students (id),
                        FOREIGN KEY(subject_id) REFERENCES subjects (id),
                        FOREIGN KEY(class_arm_id) REFERENCES class_arms (id))''')

        # Attendance summary table
        cursor.execute("""CREATE TABLE IF NOT EXISTS attendance_summary (
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
                        FOREIGN KEY (student_id) REFERENCES students (id),
                        FOREIGN KEY (class_arm_id) REFERENCES class_arms (id))""")

        # Student assessments table
        cursor.execute("""CREATE TABLE IF NOT EXISTS student_assessments (
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
                        FOREIGN KEY (student_id) REFERENCES students (id),
                        FOREIGN KEY (class_arm_id) REFERENCES class_arms (id))""")

        # Insert sample classes
        classes = [
            ("JSS 1", "JSS"),
            ("JSS 2", "JSS"),
            ("JSS 3", "JSS"),
            ("SSS 1", "SSS"),
            ("SSS 2", "SSS"),
            ("SSS 3", "SSS")
        ]

        class_arms = [
            (1, "GOLD"), (1, "DIAMOND"),
            (2, "GOLD"), (2, "DIAMOND"),
            (3, "GOLD"), (3, "DIAMOND"),
            (4, "GOLD"), (4, "DIAMOND"),
            (5, "GOLD"), (5, "DIAMOND"),
            (6, "GOLD"), (6, "DIAMOND")
        ]

        for name, level in classes:
            cursor.execute("INSERT OR IGNORE INTO classes (name, level) VALUES (?, ?)", (name, level))

        for class_id, arm in class_arms:
            cursor.execute("INSERT OR IGNORE INTO class_arms (class_id, arm) VALUES (?, ?)", (class_id, arm))

        # Initialize subjects and departments
        initialize_subjects_and_departments()
        
        # Initialize class subject requirements
        initialize_class_subject_requirements()

        db.commit()

        # 4. VERIFY THE DATA WAS INSERTED CORRECTLY
        print("=== Database Initialization Complete ===")

        # Check Classes
        cursor.execute("SELECT id, name, level FROM classes")
        print("Classes:")
        for row in cursor.fetchall():
            print(f"ID: {row['id']}, Name: {row['name']}, Level: {row['level']}")

        # Check Class Arms
        cursor.execute("SELECT id, class_id, arm FROM class_arms")
        print("\nClass Arms:")
        for row in cursor.fetchall():
            print(f"Arm ID: {row['id']}, Class ID: {row['class_id']}, Arm: {row['arm']}")

        # Check Departments
        cursor.execute("SELECT id, name, level FROM departments")
        print("\nDepartments:")
        for row in cursor.fetchall():
            print(f"Dept ID: {row['id']}, Name: {row['name']}, Level: {row['level']}")

        # Check Subjects
        cursor.execute("SELECT id, name, level, is_common_core FROM subjects ORDER BY level, name")
        print("\nSubjects:")
        for row in cursor.fetchall():
            print(f"Subject ID: {row['id']}, Name: {row['name']}, Level: {row['level']}, Common Core: {row['is_common_core']}")

        # Check Department-Subject relationships
        cursor.execute("""
            SELECT d.name as dept_name, s.name as subject_name, ds.is_compulsory
            FROM department_subjects ds
            JOIN departments d ON ds.department_id = d.id
            JOIN subjects s ON ds.subject_id = s.id
            ORDER BY d.name, ds.is_compulsory DESC, s.name
        """)
        print("\nDepartment-Subject Relationships:")
        for row in cursor.fetchall():
            print(f"Department: {row['dept_name']}, Subject: {row['subject_name']}, Compulsory: {row['is_compulsory']}")

        # Check Class-Subject requirements
        cursor.execute("""
            SELECT c.name as class_name, ca.arm, s.name as subject_name, csr.is_compulsory
            FROM class_subject_requirements csr
            JOIN class_arms ca ON csr.class_arm_id = ca.id
            JOIN classes c ON ca.class_id = c.id
            JOIN subjects s ON csr.subject_id = s.id
            ORDER BY c.name, ca.arm, s.name
        """)
        print("\nClass-Subject Requirements:")
        for row in cursor.fetchall():
            print(f"Class: {row['class_name']} {row['arm']}, Subject: {row['subject_name']}, Compulsory: {row['is_compulsory']}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_reg_number(class_name, session, term, index):
    """Generate registration number in CLASS-SESSION-TERM-SERIAL format"""
    # Extract abbreviation from class name (e.g., "JSS 1" -> "JSS1")
    class_abbr = class_name.replace(" ", "")
    
    # Convert session format from "2024/2025" to "2425" for reg number
    # Take last 2 digits of first year and first 2 digits of second year
    session_parts = session.split('/')
    if len(session_parts) == 2:
        session_short = session_parts[0][-2:] + session_parts[1][2:4]
    else:
        # Fallback if session format is unexpected
        session_short = session.replace('/', '')[:4]
    
    return f"{class_abbr}-{session_short}-{term}-{index:03d}"

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
    db = get_db()
    cursor = db.cursor()
    current_session = get_current_session()
    
    cursor.execute("""
        WITH ClassArmStudents AS (
            SELECT sc.class_arm_id, COUNT(DISTINCT sc.student_id) as student_count
            FROM student_classes sc
            WHERE sc.session = ?
            GROUP BY sc.class_arm_id
        )
        SELECT ca.id as arm_id, c.name as class_name, ca.arm,
               COALESCE(cas.student_count, 0) as student_count
        FROM class_arms ca
        JOIN classes c ON ca.class_id = c.id
        LEFT JOIN ClassArmStudents cas ON ca.id = cas.class_arm_id
        ORDER BY c.id, ca.arm
    """, (current_session,))
    
    classes_with_data = []
    for row in cursor.fetchall():
        classes_with_data.append({
            'arm_id': row['arm_id'],
            'class_name': row['class_name'],
            'arm': row['arm'],
            'has_data': row['student_count'] > 0,
            'student_count': row['student_count']
        })
    
    return classes_with_data

def get_current_session():
    """Get current academic session in YYYY/YYYY format"""
    current_year = datetime.now().year
    # If we're in second half of the year, current session is current_year/current_year+1
    if datetime.now().month >= 9:  # September or later
        return f"{current_year}/{current_year + 1}"
    else:
        return f"{current_year - 1}/{current_year}"

def get_current_term():
    """Get current term based on current month"""
    month = datetime.now().month
    if month in [1, 2, 3, 4]:
        return 3  # Third term
    elif month in [5, 6, 7, 8]:
        return 2  # Second term
    else:
        return 1  # First term

def initialize_subjects_and_departments():
    """Initialize subjects and departments with proper relationships"""
    db = get_db()
    cursor = db.cursor()

    # --- Define Departments ---
    departments = [
        ("Junior General", "junior", "All subjects for junior classes"),
        ("Science", "senior", "Science department for senior classes"),
        ("Arts/Humanities", "senior", "Arts and Humanities department"),
        ("Commercial", "senior", "Commercial/Business department")
    ]
    
    for name, level, description in departments:
        cursor.execute("""
            INSERT OR IGNORE INTO departments (name, level, description)
            VALUES (?, ?, ?)
        """, (name, level, description))
    
    # --- Define Subjects ---
    subjects_data = [
        # Junior Subjects
        ("Mathematics", "junior", 1),
        ("English", "junior", 1),
        ("Basic Science", "junior", 0),
        ("Basic Technology", "junior", 0),
        ("Business Studies", "junior", 0),
        ("Social Studies", "junior", 0),
        ("Cultural and Creative Arts", "junior", 0),
        ("Igbo", "junior", 0),
        ("Yoruba", "junior", 0),
        ("French", "junior", 0),
        ("Information and Communication Technology", "junior", 0),
        ("Music", "junior", 0),
        ("History", "junior", 0),
        ("Physical and Health Education", "junior", 0),
        ("Civic Education", "junior", 1),

        # Senior Subjects (Common Core)
        ("Mathematics", "senior", 1),
        ("English", "senior", 1),
        ("Civic Education", "senior", 1),

        # Senior Science Subjects
        ("Physics", "senior", 0),
        ("Chemistry", "senior", 0),
        ("Biology", "senior", 0),
        ("Further Mathematics", "senior", 0),
        ("Agricultural Science", "senior", 0),
        ("Geography", "senior", 0),
        ("Technical Drawing", "senior", 0),

        # Senior Arts Subjects
        ("Literature in English", "senior", 0),
        ("Government", "senior", 0),
        ("History", "senior", 0),
        ("Christian Religious Studies", "senior", 0),
        ("Islamic Religious Studies", "senior", 0),
        ("Visual Arts", "senior", 0),
        ("Music", "senior", 0),

        # Senior Commercial Subjects
        ("Economics", "senior", 0),
        ("Commerce", "senior", 0),
        ("Accounting", "senior", 0),
        ("Business Studies", "senior", 0),
        ("Financial Accounting", "senior", 0)
    ]
    
    for name, level, is_common_core in subjects_data:
        cursor.execute("""
            INSERT OR IGNORE INTO subjects (name, level, is_common_core)
            VALUES (?, ?, ?)
        """, (name, level, is_common_core))
    
    # --- Fetch IDs ---
    cursor.execute("SELECT id, name, level FROM departments")
    dept_rows = cursor.fetchall()
    departments_dict = {f"{name}_{level}": id for id, name, level in dept_rows}
    
    cursor.execute("SELECT id, name, level FROM subjects")
    subject_rows = cursor.fetchall()
    subjects_dict = {f"{name}_{level}": id for id, name, level in subject_rows}
    
    # --- Define Department-Subject Relationships ---
    # Junior General Department
    junior_dept_id = departments_dict.get("Junior General_junior")
    for key, subject_id in subjects_dict.items():
        if "_junior" in key:
            cursor.execute("""
                INSERT OR IGNORE INTO department_subjects (department_id, subject_id, is_compulsory)
                VALUES (?, ?, ?)
            """, (junior_dept_id, subject_id, 1))

    # Science Department
    science_dept_id = departments_dict.get("Science_senior")
    science_subjects = [
        "Mathematics_senior", "English_senior", "Civic Education_senior",
        "Physics_senior", "Chemistry_senior", "Biology_senior",
        "Further Mathematics_senior", "Agricultural Science_senior",
        "Geography_senior", "Technical Drawing_senior"
    ]
    for key in science_subjects:
        if key in subjects_dict:
            is_compulsory = 1 if key in ["Mathematics_senior", "English_senior", "Civic Education_senior",
                                         "Physics_senior", "Chemistry_senior"] else 0
            cursor.execute("""
                INSERT OR IGNORE INTO department_subjects (department_id, subject_id, is_compulsory)
                VALUES (?, ?, ?)
            """, (science_dept_id, subjects_dict[key], is_compulsory))

    # Arts Department
    arts_dept_id = departments_dict.get("Arts/Humanities_senior")
    arts_subjects = [
        "Mathematics_senior", "English_senior", "Civic Education_senior",
        "Literature in English_senior", "Government_senior", "History_senior",
        "Christian Religious Studies_senior", "Islamic Religious Studies_senior",
        "Visual Arts_senior", "Music_senior", "Geography_senior"
    ]
    for key in arts_subjects:
        if key in subjects_dict:
            is_compulsory = 1 if key in ["Mathematics_senior", "English_senior", "Civic Education_senior",
                                         "Literature in English_senior"] else 0
            cursor.execute("""
                INSERT OR IGNORE INTO department_subjects (department_id, subject_id, is_compulsory)
                VALUES (?, ?, ?)
            """, (arts_dept_id, subjects_dict[key], is_compulsory))

    # Commercial Department
    commercial_dept_id = departments_dict.get("Commercial_senior")
    commercial_subjects = [
        "Mathematics_senior", "English_senior", "Civic Education_senior",
        "Economics_senior", "Commerce_senior", "Accounting_senior",
        "Business Studies_senior", "Financial Accounting_senior",
        "Geography_senior"
    ]
    for key in commercial_subjects:
        if key in subjects_dict:
            is_compulsory = 1 if key in ["Mathematics_senior", "English_senior",
                                         "Civic Education_senior", "Economics_senior"] else 0
            cursor.execute("""
                INSERT OR IGNORE INTO department_subjects (department_id, subject_id, is_compulsory)
                VALUES (?, ?, ?)
            """, (commercial_dept_id, subjects_dict[key], is_compulsory))

    # --- Assign Subjects to Each Class Arm ---
    cursor.execute("""
        SELECT ca.id AS id, c.name AS class_name, ca.arm AS arm, c.level AS level
        FROM class_arms ca
        JOIN classes c ON ca.class_id = c.id
    """)
    class_arms = cursor.fetchall()

    for class_arm in class_arms:
        class_arm_id = class_arm["id"]
        class_name = class_arm["class_name"].lower()

        if "jss" in class_name:
            dept_key = "Junior General_junior"
        elif "sss" in class_name:
            # detect type of senior class if possible
            if "science" in class_name:
                dept_key = "Science_senior"
            elif "arts" in class_name:
                dept_key = "Arts/Humanities_senior"
            elif "commercial" in class_name:
                dept_key = "Commercial_senior"
            else:
                dept_key = "Science_senior"  # default
        else:
            continue

        dept_id = departments_dict.get(dept_key)
        if not dept_id:
            continue

        cursor.execute("""
            SELECT subject_id, is_compulsory
            FROM department_subjects
            WHERE department_id = ?
        """, (dept_id,))
        dept_subjects = cursor.fetchall()

        for subj in dept_subjects:
            cursor.execute("""
                INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory)
                VALUES (?, ?, ?)
            """, (class_arm_id, subj["subject_id"], subj["is_compulsory"]))

    db.commit()
    print("Subjects, departments, and class-subject links initialized successfully.")

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
            
            # For now, add common core subjects to all senior classes
            cursor.execute("""
                INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory)
                SELECT ?, s.id, 1
                FROM subjects s
                WHERE s.level = 'senior' AND s.is_common_core = 1
            """, (arm_id,))
    
    db.commit()
    print("Class subject requirements initialized")


# Routes
@app.route('/')
def home():
    current_session = get_current_session()
    current_term = get_current_term()
    return render_template('home.html', 
                         current_year=datetime.now().year,
                         session=current_session,
                         term=current_term)

@app.route('/uploads/photos/<filename>')
def serve_uploaded_photo(filename):
    """Serve uploaded photos from the uploads directory"""
    try:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), filename)
    except FileNotFoundError:
        # Return a default image or 404 if the file doesn't exist
        return "Image not found", 404
    
# Student Biodata Management
@app.route('/manage-students')
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

@app.route('/upload-students', methods=['POST'])
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

def process_student_upload(filepath, class_arm_id, session, term):
    errors = []
    success_count = 0
    db = get_db()

    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]

        # Check for required columns
        required_cols = {'full_name'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return errors, success_count

        # Check if optional columns exist
        has_gender = 'gender' in df.columns
        has_department = 'department' in df.columns

        cursor = db.cursor()
        
        # Get class info including level
        cursor.execute("""
            SELECT c.id as class_id, c.name as class_name, c.level
            FROM classes c 
            JOIN class_arms ca ON c.id = ca.class_id 
            WHERE ca.id = ?
        """, (class_arm_id,))
        class_info = cursor.fetchone()
        
        if not class_info:
            errors.append("Invalid class selected")
            return errors, success_count

        class_name = class_info['class_name']
        class_level = class_info['level']  # 'JSS' or 'SSS'

        # Get existing students for this class/session/term to prevent duplicates
        cursor.execute("""
            SELECT LOWER(TRIM(s.full_name)) as lower_name, s.full_name as original_name
            FROM students s
            JOIN student_classes sc ON s.id = sc.student_id
            WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ?
        """, (class_arm_id, session, term))
        
        existing_students = {row['lower_name']: row['original_name'] for row in cursor.fetchall()}
        
        if existing_students:
            errors.append(f"Found {len(existing_students)} existing students in this class. New students will be added.")

        # Process each row
        processed_names = set()
        new_students = []
        
        for _, row in df.iterrows():
            full_name = str(row['full_name']).strip()
            full_name_lower = full_name.lower()
            
            # Skip empty names
            if not full_name:
                continue
                
            # Skip duplicates within the same file
            if full_name_lower in processed_names:
                errors.append(f"Duplicate in file skipped: {full_name}")
                continue
            processed_names.add(full_name_lower)
            
            # Skip if student already exists in this class
            if full_name_lower in existing_students:
                errors.append(f"Already exists skipped: {full_name}")
                continue
                
            # Extract gender
            gender = None
            if has_gender and 'gender' in row and not pd.isna(row['gender']):
                gender_val = str(row['gender']).strip().lower()
                if gender_val in ['male', 'm', 'boy']:
                    gender = 'Male'
                elif gender_val in ['female', 'f', 'girl']:
                    gender = 'Female'
                
            # Extract department
            dept_name = None
            if has_department and 'department' in row and not pd.isna(row['department']):
                dept_name = str(row['department']).strip()
                
            new_students.append({
                'full_name': full_name,
                'age': int(row['age']) if 'age' in df.columns and not pd.isna(row['age']) else None,
                'department': dept_name,
                'gender': gender
            })

        if not new_students:
            errors.append("No new students to add. All students in the file already exist in this class.")
            return errors, success_count

        # Get the next registration number index
        cursor.execute("""
            SELECT MAX(CAST(SUBSTR(reg_number, INSTR(reg_number, '-') + 1, 4) AS INTEGER)) as max_index
            FROM students 
            WHERE reg_number LIKE ? AND reg_number LIKE ?
        """, (f"{class_name.replace(' ', '')}%", f"%{session.replace('/', '')[2:6]}%"))
        
        result = cursor.fetchone()
        start_index = result['max_index'] + 1 if result and result['max_index'] else 1

        # Get department mapping
        cursor.execute("SELECT id, name, level FROM departments")
        depts = cursor.fetchall()
        dept_dict = {name.lower(): id for id, name, level in depts}

        # Insert new students
        for i, student_data in enumerate(new_students, start=start_index):
            try:
                full_name = student_data['full_name']
                age = student_data['age']
                dept_name = student_data['department']
                gender = student_data['gender']
                
                # Determine department based on class level and uploaded data
                department_id = None
                
                if class_level == "JSS":
                    # Junior students go to Junior General department
                    cursor.execute("SELECT id FROM departments WHERE name = 'Junior General'")
                    result = cursor.fetchone()
                    if result:
                        department_id = result['id']
                    else:
                        errors.append(f"Junior General department not found for {full_name}")
                        continue
                else:
                    # Senior students - determine department from upload
                    if dept_name:
                        dept_name_lower = dept_name.lower()
                        if any(keyword in dept_name_lower for keyword in ['sci', 'physics', 'chem', 'bio']):
                            cursor.execute("SELECT id FROM departments WHERE name = 'Science'")
                            result = cursor.fetchone()
                            if result:
                                department_id = result['id']
                        elif any(keyword in dept_name_lower for keyword in ['art', 'human', 'literature', 'history', 'government']):
                            cursor.execute("SELECT id FROM departments WHERE name = 'Arts/Humanities'")
                            result = cursor.fetchone()
                            if result:
                                department_id = result['id']
                        elif any(keyword in dept_name_lower for keyword in ['comm', 'business', 'account', 'economic']):
                            cursor.execute("SELECT id FROM departments WHERE name = 'Commercial'")
                            result = cursor.fetchone()
                            if result:
                                department_id = result['id']
                
                # If no department specified for senior, use Science as default
                if class_level == "SSS" and not department_id:
                    cursor.execute("SELECT id FROM departments WHERE name = 'Science'")
                    result = cursor.fetchone()
                    if result:
                        department_id = result['id']
                    else:
                        errors.append(f"No Science department found for {full_name}")
                        continue
                
                # For senior students, add department-specific subjects to class requirements
                if class_level == "SSS" and department_id:
                    cursor.execute("""
                        INSERT OR IGNORE INTO class_subject_requirements (class_arm_id, subject_id, is_compulsory)
                        SELECT ?, ds.subject_id, ds.is_compulsory
                        FROM department_subjects ds
                        WHERE ds.department_id = ?
                    """, (class_arm_id, department_id))
                
                reg_number = generate_reg_number(class_name, session, term, i)
                
                cursor.execute('''INSERT OR IGNORE INTO students 
                                  (reg_number, full_name, age, gender, photo, department_id) 
                                  VALUES (?, ?, ?, ?, ?, ?)''',
                               (reg_number, full_name, age, gender, None, department_id))

                student_row = cursor.execute("SELECT id FROM students WHERE full_name = ?", 
                                             (full_name,)).fetchone()
                if student_row:
                    cursor.execute('''INSERT OR IGNORE INTO student_classes 
                                      (student_id, class_arm_id, session, term) 
                                      VALUES (?, ?, ?, ?)''',
                                   (student_row['id'], class_arm_id, session, term))
                    success_count += 1
                    
            except Exception as e:
                errors.append(f"Error processing {full_name}: {str(e)}")

        db.commit()

    except Exception as e:
        errors.append(f"File processing error: {str(e)}")

    return errors, success_count

@app.route('/upload-student-photo/<reg_number>', methods=['POST'])
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
            
            # Generate secure filename with proper extension
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            filename = secure_filename(f"{reg_number}.{file_ext}")
            photo_path = os.path.join(upload_dir, filename)
            
            # Save the file
            file.save(photo_path)
            
            # Update student record
            cursor.execute("UPDATE students SET photo = ? WHERE reg_number = ?", (filename, reg_number))
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

@app.route('/students')
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

    db = get_db()
    cursor = db.cursor()

    # Fetch all class arms for dropdown
    cursor.execute("""
        SELECT a.id AS arm_id, c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
    """)
    classes = cursor.fetchall()

    cursor.execute("SELECT DISTINCT session FROM student_classes ORDER BY session DESC")
    sessions = [row['session'] for row in cursor.fetchall()]
    if session_filter not in sessions:
        sessions.insert(0, session_filter)

    # Build query based on filters
    if class_filter == "all":
        cursor.execute("""
            SELECT s.reg_number, s.full_name, s.age, s.photo, 
                   c.name || ' ' || a.arm AS class_name, sc.term, sc.session
            FROM students s
            JOIN student_classes sc ON s.id = sc.student_id
            JOIN class_arms a ON sc.class_arm_id = a.id
            JOIN classes c ON a.class_id = c.id
            WHERE sc.session = ?
            ORDER BY s.full_name
        """, (session_filter,))
    else:
       cursor.execute("""
            SELECT s.reg_number, s.full_name, s.age, s.photo, 
                   c.name || ' ' || a.arm AS class_name, sc.term, sc.session
            FROM students s
            JOIN student_classes sc ON s.id = sc.student_id
            JOIN class_arms a ON sc.class_arm_id = a.id
            JOIN classes c ON a.class_id = c.id
            WHERE sc.session = ? AND sc.term = ? AND sc.class_arm_id = ?
            ORDER BY s.full_name
        """, (session_filter, term_filter, class_filter))

    students = cursor.fetchall()

    return render_template('students.html',
                          students=students,
                          classes=classes,
                          sessions=sessions,
                          selected_class=class_filter,
                          selected_session=session_filter,
                          selected_term=term_filter
                          )

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

        required_cols = {'full_name', 'ca1_score', 'ca2_score', 'ca3_score', 'ca4_score', 'exam_score'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return errors, success_count

        cursor = db.cursor()
        subject_name = cursor.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()['name']

        for _, row in df.iterrows():
            try:
                full_name = row['full_name'].strip()
                
                # Get all scores
                ca1_score = float(row['ca1_score']) if not pd.isna(row['ca1_score']) else 0
                ca2_score = float(row['ca2_score']) if not pd.isna(row['ca2_score']) else 0
                ca3_score = float(row['ca3_score']) if not pd.isna(row['ca3_score']) else 0
                ca4_score = float(row['ca4_score']) if not pd.isna(row['ca4_score']) else 0
                exam_score = float(row['exam_score']) if not pd.isna(row['exam_score']) else 0
                
                # Validate scores
                if not (0 <= ca1_score <= 5):
                    errors.append(f"Invalid CA1 score for {full_name}: {ca1_score}. Must be between 0-5")
                    continue
                if not (0 <= ca2_score <= 5):
                    errors.append(f"Invalid CA2 score for {full_name}: {ca2_score}. Must be between 0-5")
                    continue
                if not (0 <= ca3_score <= 5):
                    errors.append(f"Invalid CA3 score for {full_name}: {ca3_score}. Must be between 0-5")
                    continue
                if not (0 <= ca4_score <= 5):
                    errors.append(f"Invalid CA4 score for {full_name}: {ca4_score}. Must be between 0-5")
                    continue
                if not (0 <= exam_score <= 80):
                    errors.append(f"Invalid exam score for {full_name}: {exam_score}. Must be between 0-80")
                    continue

                # Calculate total score for full-term
                total_score = ca1_score + ca2_score + ca3_score + ca4_score + exam_score

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

                # Insert or update full-term scores
                cursor.execute('''INSERT OR REPLACE INTO scores 
                                  (student_id, subject_id, class_arm_id, term, session,
                                   ca1_score, ca2_score, ca3_score, ca4_score, exam_score, total_score, report_type, created_at) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (student_id, subject_id, class_arm_id, term, session,
                                ca1_score, ca2_score, ca3_score, ca4_score, exam_score, total_score, 'full_term', now))

                success_count += 1
                
            except Exception as e:
                errors.append(f"Error processing {full_name}: {str(e)}")

        db.commit()

    except Exception as e:
        errors.append(f"File processing error: {str(e)}")

    return errors, success_count

@app.route('/upload-half-term-results')
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

@app.route('/process-half-term-results', methods=['POST'])
def process_half_term_results():
    subject_id = request.form['subject_id']
    class_arm_id = request.form['class_arm_id']
    term = request.form['term']
    session = request.form['session']

    if 'file' not in request.files:
        return redirect(url_for('upload_half_term_results'))

    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('upload_half_term_results'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        errors, success_count = process_half_term_upload(filepath, subject_id, class_arm_id, term, session)

        if errors:
            return render_template('upload_error.html', errors=errors, success_count=success_count)

        return render_template('upload_success.html',
                              success_count=success_count,
                              message=f"{success_count} half-term scores uploaded")

    return redirect(url_for('upload_half_term_results'))

@app.route('/upload-full-term-results')
def upload_full_term_results():
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

    return render_template('upload_full_term_results.html',
                          subjects=subjects,
                          classes=classes,
                          current_session=current_session)

@app.route('/process-full-term-results', methods=['POST'])
def process_full_term_results():
    subject_id = request.form['subject_id']
    class_arm_id = request.form['class_arm_id']
    term = request.form['term']
    session = request.form['session']

    if 'file' not in request.files:
        return redirect(url_for('upload_full_term_results'))

    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('upload_full_term_results'))

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

    return redirect(url_for('upload_full_term_results'))

@app.route('/results')
def view_results():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT s.reg_number, s.full_name, 
               c.name || ' - ' || ca.arm AS class_name,  -- Combine class name and arm
               sub.name AS subject, sc.total_score, sc.term, sc.session
        FROM scores sc
        JOIN students s ON sc.student_id = s.id
        JOIN subjects sub ON sc.subject_id = sub.id
        JOIN class_arms ca ON sc.class_arm_id = ca.id
        JOIN classes c ON ca.class_id = c.id
        ORDER BY sc.session DESC, sc.term DESC, c.name, ca.arm, s.full_name
    ''')
    results = cursor.fetchall()
    return render_template('results.html', results=results)

@app.route('/generate-reports', methods=['GET', 'POST'])
def generate_reports():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        class_arm_id = request.form.get('class_arm_id')
        term = int(request.form['term'])
        session = request.form['session']
        report_type = request.form.get('report_type', 'full_term')

        # --- Single Student Report ---
        if full_name:
            cursor.execute("""
                    SELECT s.*, c.name || ' ' || a.arm AS class_name
                    FROM students s
                    JOIN student_classes sc ON s.id = sc.student_id
                    JOIN class_arms a ON sc.class_arm_id = a.id
                    JOIN classes c ON a.class_id = c.id
                    WHERE sc.class_arm_id = ? AND sc.session = ? 
                        AND LOWER(s.full_name) = LOWER(?)
                """, (class_arm_id, session, full_name.strip()))
            student = cursor.fetchone()

            if not student:
                return render_template("error.html", message="Student not found")

            cursor.execute("""
                    SELECT sub.name AS subject, 
                           sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score, 
                           sc.exam_score, sc.total_score, sc.report_type
                    FROM scores sc
                    JOIN subjects sub ON sc.subject_id = sub.id
                    WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ? AND sc.report_type = ?
                """, (student["id"], term, session, report_type))
            scores = cursor.fetchall()

            if not scores:
                return render_template("error.html", message="No results found")

            cursor.execute("""
                    SELECT days_present, days_absent, days_late, total_school_days
                    FROM attendance_summary 
                    WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
                """, (student['id'], class_arm_id, term, session))
            attendance_summary = cursor.fetchone()

            cursor.execute("""
                SELECT handwriting, sports_participation, practical_skills,
                    punctuality, politeness, neatness,
                    class_teacher_comment, principal_comment
                FROM student_assessments
                WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
            """, (student["id"], class_arm_id, term, session))
            assessment = cursor.fetchone()

            total = sum(r["total_score"] for r in scores)
            average = total / len(scores)
            
            # Choose template based on report type
            template_name = "half_term_report.html" if report_type == "half_term" else "full_term_report.html"
            logo_path = os.path.join(app.root_path, 'static', 'kembos_logo_nobg.png')
            photo_path = os.path.join(app.root_path, 'uploads', student['photo']) if student['photo'] else None
            
            # html_content = render_template(template_name,
            #                                student=student,
            #                                class_name=student["class_name"],
            #                                scores=scores,
            #                                term=term,
            #                                logo_path=logo_path,
            #                                photo_path=photo_path,
            #                                session=session,
            #                                average=average,
            #                                report_type=report_type,
            #                                attendance_summary=attendance_summary,
            #                                year=datetime.now().year,
            #                                current_date=datetime.now().strftime("%Y-%m-%d"))

            # pdf_file = f"{student['full_name']}_report.pdf"
            # pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file)
            # HTML(string=html_content, base_url=request.host_url).write_pdf(pdf_path)

            # return send_file(pdf_path, as_attachment=True)

            return render_template(template_name,
                                           student=student,
                                           class_name=student["class_name"],
                                           scores=scores,
                                           term=term,
                                           logo_path=logo_path,
                                           photo_path=photo_path,
                                           session=session,
                                           average=average,
                                           report_type=report_type,
                                           attendance_summary=attendance_summary,
                                           assessment=assessment,
                                           year=datetime.now().year,
                                           current_date=datetime.now().strftime("%Y-%m-%d"))

       # --- Whole Class Batch Reports ---
        cursor.execute("""
            SELECT s.id, s.reg_number, s.full_name, s.age, s.photo, 
                c.name || ' ' || a.arm AS class_name
            FROM students s
            JOIN student_classes sc ON s.id = sc.student_id
            JOIN class_arms a ON sc.class_arm_id = a.id
            JOIN classes c ON a.class_id = c.id
            WHERE sc.class_arm_id = ? AND sc.session = ?
            ORDER BY s.full_name
        """, (class_arm_id, session))
        students = cursor.fetchall()

        if not students:
            return render_template("error.html", message="No students found for this class/year")

        report_type = request.form.get("report_type", "full_term")

        # Sanitize ZIP filename
        safe_session = session.replace("/", "_")
        zip_filename = f"class_{class_arm_id}_term{term}_{safe_session}_reports.zip"

        # Prepare in-memory ZIP buffer
        zip_buffer = BytesIO()

        # Detect your current host (local or LAN)
        host_url = request.host_url.rstrip('/')

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for student in students:
                    reg_number = student["reg_number"]
                    
                    # Construct the exact URL for the student's report page
                    report_url = f"{host_url}/preview-report?student_id={student['id']}&term={term}&session={session}&report_type={report_type}"
                    
                    pdf_filename = f"{student['full_name'].replace(' ', '_')}_report.pdf"
                    pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
                    
                    page = context.new_page()
                    print(f"🧾 Generating PDF for {student['full_name']} ({report_type})")
                    
                    try:
                        page.goto(report_url, wait_until="networkidle")
                        page.pdf(
                            path=pdf_path,
                            format="A4",
                            print_background=True,
                            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
                        )
                        zf.write(pdf_path, pdf_filename)
                    except Exception as e:
                        print(f"❌ Error generating report for {student['full_name']}: {e}")
                    finally:
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)
                        page.close()
            
            browser.close()

        # Return ZIP as downloadable file
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=zip_filename,
            mimetype="application/zip"
        )


    # --- GET request → show report form ---
    cursor.execute("""
                SELECT a.id AS arm_id, c.name AS class_name, a.arm
                FROM class_arms a
                JOIN classes c ON a.class_id = c.id
                ORDER BY c.id, a.arm
            """)
    classes = cursor.fetchall()
    current_session=get_current_session()
    return render_template("report_form.html", classes=classes, current_session=current_session)

@app.route("/preview-report")
def preview_report():
    student_id = request.args.get("student_id")
    term = request.args.get("term")
    session = request.args.get("session")
    report_type = request.args.get("report_type", "full_term")

    if not student_id or not term or not session:
        return "Missing parameters", 400

    db = get_db()
    cursor = db.cursor()

    # Get student info
    cursor.execute("""
        SELECT s.id, s.reg_number, s.full_name, s.age, s.photo, 
               c.name || ' ' || a.arm AS class_name, s.department_id, s.gender
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        JOIN class_arms a ON sc.class_arm_id = a.id
        JOIN classes c ON a.class_id = c.id
        WHERE s.id = ? AND sc.session = ?
    """, (student_id, session))
    student = cursor.fetchone()
    if not student:
        return "Student not found", 404

    # Get scores
    cursor.execute("""
        SELECT sub.name AS subject, 
               sc.ca1_score, sc.ca2_score, sc.ca3_score, sc.ca4_score,
               sc.exam_score, sc.total_score
        FROM scores sc
        JOIN subjects sub ON sc.subject_id = sub.id
        WHERE sc.student_id = ? AND sc.term = ? AND sc.session = ? AND sc.report_type = ?
    """, (student_id, term, session, report_type))
    scores = cursor.fetchall()

    # Get attendance
    cursor.execute("""
        SELECT days_present, days_absent, days_late, total_school_days
        FROM attendance_summary 
        WHERE student_id = ? AND class_arm_id = (
            SELECT class_arm_id FROM student_classes 
            WHERE student_id = ? AND session = ?
        )
        AND term = ? AND session = ?
    """, (student_id, student_id, session, term, session))
    attendance_summary = cursor.fetchone()

    cursor.execute("""
        SELECT handwriting, sports_participation, practical_skills,
            punctuality, politeness, neatness,
            class_teacher_comment, principal_comment
        FROM student_assessments
        WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
    """, (student["id"], class_arm_id, term, session))
    assessment = cursor.fetchone()

    total = sum(r["total_score"] or 0 for r in scores) if scores else 0
    average = total / len(scores) if scores else 0

    template_name = "full_term_report.html" if report_type == "full_term" else "half_term_report.html"

    return render_template(template_name,
                           student=student,
                           class_name=student["class_name"],
                           scores=scores,
                           term=term,
                           session=session,
                           average=average,
                           report_type=report_type,
                           attendance_summary=attendance_summary,
                           assessment=assessment,
                           year=datetime.now().year,
                           current_date=datetime.now().strftime("%Y-%m-%d"))

@app.route('/download-student-template')
def download_student_template():
    """
    Download Excel template for class teachers to upload student biodata.
    """
    sample_data = {
        'full_name': ['John Doe', 'Jane Smith', 'Mike Johnson'],
        'age': [15, 16, 14],
        'gender': ['Male', 'Female', 'Male'],
        'department': ['Science', 'Arts', 'Commercial']
    }
    df = pd.DataFrame(sample_data)

    # Write to Excel (BytesIO for in-memory download)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Student_Data', index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='student_upload_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/download-result-template')
def download_result_template():
    """Download Excel template for result uploads (auto formulas + locked names)."""
    class_arm_id = request.args.get('class_arm_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    term = request.args.get('term')
    session = request.args.get('session')

    if not all([class_arm_id, subject_id, term, session]):
        abort(400, description="Missing required parameters")

    db = get_db()
    cursor = db.cursor()

    # --- Subject & Class Info ---
    cursor.execute("""
        SELECT s.name AS subject_name, c.name AS class_name, a.arm
        FROM subjects s
        JOIN class_arms a ON a.id = ?
        JOIN classes c ON a.class_id = c.id
        WHERE s.id = ?
    """, (class_arm_id, subject_id))
    info = cursor.fetchone()
    if not info:
        abort(404, description="Invalid class or subject selection")

    # --- Get Students ---
    cursor.execute("""
        SELECT st.full_name
        FROM students st
        JOIN student_classes sc ON st.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.session = ? AND sc.term = ?
        ORDER BY st.full_name
    """, (class_arm_id, session, term))
    students = cursor.fetchall()
    if not students:
        abort(404, description="No students found for this class/session")

    # --- Create DataFrame ---
    data = {
        'Full Name': [s['full_name'] for s in students],
        'CA1': [''] * len(students),
        'CA2': [''] * len(students),
        'CA3': [''] * len(students),
        'CA4': [''] * len(students),
        'CA Total': [''] * len(students),
        'Exam': [''] * len(students),
        'Total': [''] * len(students)
    }
    df = pd.DataFrame(data)

    # --- Write to Excel ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Results', index=False)
    output.seek(0)

    # --- Load workbook for styling, formulas, and protection ---
    wb = load_workbook(output)
    ws = wb.active

    # --- Header Styling ---
    header_fill = PatternFill(start_color="1E3C72", end_color="1E3C72", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # --- Insert Formulas ---
    ca_total_col = 6  # F
    exam_col = 7      # G
    total_col = 8     # H
    num_students = len(students)

    for i in range(2, num_students + 2):
        # CA Total = SUM(B:E)
        ws.cell(row=i, column=ca_total_col).value = f"=SUM(B{i}:E{i})"
        # Total = F + G
        ws.cell(row=i, column=total_col).value = f"=F{i}+G{i}"

    # --- Freeze header row ---
    ws.freeze_panes = "A2"

    # --- Auto column width ---
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[column].width = max_length + 2

    # --- Protect sheet ---
    ws.protection.sheet = True
    ws.protection.password = "kembos"  # You can change this password if you want

    # Make only "Full Name" column locked, others editable
    for row in ws.iter_rows(min_row=2, max_row=num_students + 1, min_col=1, max_col=8):
        for cell in row:
            if cell.column == 1:  # Full Name
                cell.protection = Protection(locked=True)
            else:
                cell.protection = Protection(locked=False)

    # --- Save to memory ---
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"result_template_{info['class_name']}_{info['arm']}_{info['subject_name']}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename.replace(" ", "_"),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/class-teacher')
def class_teacher_portal():
    db = get_db()
    cursor = db.cursor()
    current_session = get_current_session()
    current_term = get_current_term()
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Get all class arms for the dropdown
    cursor.execute("""
        SELECT a.id AS arm_id, c.name AS class_name, a.arm, c.level
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
    """)
    classes = cursor.fetchall()
    
    return render_template('class_teacher_portal.html', 
                         classes=classes,
                         current_session=current_session,
                         current_term=current_term,
                         current_date=current_date)

def get_upload_status(class_arm_id, term, session, report_type='full_term'):
    """Get upload status for all subjects in a class"""
    db = get_db()
    cursor = db.cursor()

    # Get all subjects required for this class
    cursor.execute("""
        SELECT s.id, s.name, s.is_common_core, csr.is_compulsory
        FROM subjects s
        JOIN class_subject_requirements csr ON s.id = csr.subject_id
        WHERE csr.class_arm_id = ?
        ORDER BY s.name
    """, (class_arm_id,))
    subjects = cursor.fetchall()

    # Get number of students in the class
    cursor.execute("""
        SELECT COUNT(*) as student_count
        FROM student_classes
        WHERE class_arm_id = ? AND session = ? AND term = ?
    """, (class_arm_id, session, term))
    result = cursor.fetchone()
    total_students = result['student_count'] if result else 0

    upload_status = []

    for subject in subjects:
        # Count how many students have scores for this subject and report type
        cursor.execute("""
            SELECT COUNT(DISTINCT sc.student_id) as uploaded_count
            FROM scores sc
            JOIN student_classes sclass ON sc.student_id = sclass.student_id
            WHERE sclass.class_arm_id = ? 
              AND sc.subject_id = ? 
              AND sc.term = ? 
              AND sc.session = ? 
              AND sc.report_type = ?
        """, (class_arm_id, subject['id'], term, session, report_type))
        result = cursor.fetchone()
        uploaded_count = result['uploaded_count'] if result else 0

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
            'subject_id': subject['id'],
            'subject_name': subject['name'],
            'is_required': subject['is_compulsory'],
            'uploaded_count': uploaded_count,
            'total_students': total_students,
            'completion_percentage': completion_percentage,
            'status': status
        })

    return upload_status

@app.route('/subject-teacher')
def subject_teacher_portal():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cursor.fetchall()

    # cursor.execute("""
    #     SELECT a.id AS arm_id, c.name AS class_name, a.arm
    #     FROM class_arms a
    #     JOIN classes c ON a.class_id = c.id
    #     ORDER BY c.id, a.arm
    # """)
    # classes = cursor.fetchall()

    classes_with_data = get_class_status()

    # Optional: fetch last 10 uploads
    cursor.execute("""
        SELECT s.name AS subject_name,
            c.name AS class_name,
            a.arm AS arm,
            sc.term,
            sc.session,
            MAX(sc.created_at) as date_uploaded
        FROM scores sc
        JOIN subjects s ON sc.subject_id = s.id
        JOIN class_arms a ON sc.class_arm_id = a.id
        JOIN classes c ON a.class_id = c.id
        GROUP BY s.name, c.name, a.arm, sc.term, sc.session
        ORDER BY date_uploaded DESC
        LIMIT 10
    """)
    recent_uploads = cursor.fetchall()

    current_session = get_current_session()

    return render_template(
        'subject_teacher_portal.html',
        subjects=subjects,
        classes=classes_with_data,
        current_session=current_session,
        recent_uploads=recent_uploads
    )

@app.route('/class-teacher/class/<int:class_arm_id>/<path:session>/<int:term>')
def class_teacher_class_view(class_arm_id, session, term):
    db = get_db()
    cursor = db.cursor()
    
    # Get class information
    cursor.execute("""
        SELECT c.name AS class_name, a.arm, c.level
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        WHERE a.id = ?
    """, (class_arm_id,))
    class_info = cursor.fetchone()
    
    # Get students in this class
    cursor.execute("""
        SELECT s.id, s.reg_number, s.full_name, s.age, s.gender, s.photo, s.department_id,
               d.name as department_name
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        LEFT JOIN departments d ON s.department_id = d.id
        WHERE sc.class_arm_id = ? AND sc.session = ?
        ORDER BY s.full_name
    """, (class_arm_id, session))
    students = cursor.fetchall()
    
    # Get attendance summary for each student
    # attendance_data = {}
    # for student in students:
    #     cursor.execute("""
    #         SELECT 
    #             COUNT(CASE WHEN status = 'present' THEN 1 END) as present,
    #             COUNT(CASE WHEN status = 'absent' THEN 1 END) as absent,
    #             COUNT(CASE WHEN status = 'late' THEN 1 END) as late
    #         FROM attendance 
    #         WHERE student_id = ? AND class_arm_id = ? AND term = ? AND year = ?
    #     """, (student['id'], class_arm_id, term, year))
    #     attendance_data[student['id']] = cursor.fetchone()
    
    # Get assessment data
    assessment_data = {}
    for student in students:
        cursor.execute("""
            SELECT * FROM student_assessments 
            WHERE student_id = ? AND class_arm_id = ? AND term = ? AND session = ?
        """, (student['id'], class_arm_id, term, session))
        assessment_data[student['id']] = cursor.fetchone()

    half_term_status = get_upload_status(class_arm_id, term, session, 'half_term')
    full_term_status = get_upload_status(class_arm_id, term, session, 'full_term')

    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('class_teacher_class_view.html',
                         class_info=class_info,
                         students=students,
                        #  attendance_data=attendance_data,
                        half_term_status=half_term_status,
                         full_term_status=full_term_status,
                         assessment_data=assessment_data,
                         class_arm_id=class_arm_id,
                         session=session,
                         term=term,
                         current_date=current_date) 

@app.route('/attendance/sheet/<int:class_arm_id>')
@app.route('/attendance/sheet/<int:class_arm_id>/<string:date>/<int:term>')
def attendance_sheet(class_arm_id, date=None, term=get_current_term()):
    db = get_db()
    cursor = db.cursor()
    
    # If date is not provided, use today's date
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # Get class information
    cursor.execute("""
        SELECT c.name AS class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        WHERE a.id = ?
    """, (class_arm_id,))
    class_info = cursor.fetchone()
    
    if not class_info:
        return redirect(url_for('class_teacher_portal'))
    
    # Get students in class
    cursor.execute("""
        SELECT s.id, s.reg_number, s.full_name, s.photo
        FROM students s
        JOIN student_classes sc ON s.id = sc.student_id
        WHERE sc.class_arm_id = ? AND sc.year = ?
        ORDER BY s.full_name
    """, (class_arm_id, datetime.now().year))
    students = cursor.fetchall()
    
    # Get existing attendance for this date
    cursor.execute("""
        SELECT student_id, status FROM attendance 
        WHERE class_arm_id = ? AND date = ? AND term = ? AND year = ?
    """, (class_arm_id, date, term, datetime.now().year))
    existing_attendance = {row['student_id']: row['status'] for row in cursor.fetchall()}
    
    return render_template('attendance_sheet.html',
                         students=students,
                         class_info=class_info,
                         class_arm_id=class_arm_id,
                         date=date,
                         term=term,
                         existing_attendance=existing_attendance)

@app.route('/attendance/submit', methods=['POST'])
def submit_attendance():
    class_arm_id = request.form['class_arm_id']
    date = request.form['date']
    term = request.form['term']
    year = datetime.now().year
    
    db = get_db()
    cursor = db.cursor()
    
    for key, value in request.form.items():
        if key.startswith('status_'):
            student_id = key.replace('status_', '')
            
            # Delete existing record for this student/date
            cursor.execute("""
                DELETE FROM attendance 
                WHERE student_id = ? AND class_arm_id = ? AND date = ? AND term = ? AND year = ?
            """, (student_id, class_arm_id, date, term, year))
            
            # Insert new record
            if value in ['present', 'absent', 'late']:
                cursor.execute("""
                    INSERT INTO attendance (student_id, class_arm_id, date, status, term, year)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (student_id, class_arm_id, date, value, term, year))
    
    db.commit()
    return redirect(url_for('class_teacher_portal'))

@app.route('/attendance/redirect')
def attendance_sheet_redirect():
    class_arm_id = request.args.get('class_arm_id')
    date = request.args.get('date')
    term = request.args.get('term')
    
    if not all([class_arm_id, date, term]):
        return redirect(url_for('class_teacher_portal'))
    
    return redirect(url_for('attendance_sheet', 
                        class_arm_id=class_arm_id, 
                        date=date, 
                        term=term))

@app.route('/assessments/bulk/<int:class_arm_id>/<int:term>/<path:session>')
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
    
    return render_template('bulk_assessments.j2',
                         class_info=class_info,
                         students=students,
                         assessment_data=assessment_data,
                         class_arm_id=class_arm_id,
                         term=term,
                         current_session=session)

@app.route('/assessments/submit-bulk', methods=['POST'])
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
    """, (class_arm_id, session, term))
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
    
    db.commit()
    
    return redirect(url_for('class_teacher_class_view', 
                          class_arm_id=class_arm_id, 
                          session=session, 
                          term=term))

@app.route('/attendance/summary/<int:class_arm_id>/<int:term>/<path:session>')
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

@app.route('/attendance/submit-summary', methods=['POST'])
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


@app.route('/student-photos')
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


def allowed_photo_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png', 'gif'}

if __name__ == "__main__":
    init_db()
    # Automatically get your local network IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print(f"\n🚀 Server running on:")
    print(f"   Local:     http://127.0.0.1:5000")
    print(f"   Network:   http://{local_ip}:5000\n")
    print("📡 Connect other devices on the same Wi-Fi using the 'Network' address above.\n")

    # Run Flask on all interfaces (so others can access it)
    app.run(host="0.0.0.0", port=5000, debug=True)
