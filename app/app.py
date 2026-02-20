import os
import socket

from flask import Flask, render_template, request, redirect, abort, url_for, g, session, flash, send_file, send_from_directory
from werkzeug.utils import secure_filename


from datetime import datetime

import sqlite3
import base64

from datetime import datetime

from .extensions import db, login_manager


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from app.extensions import db, login_manager
    from app.models import *
    from app.auth.routes import auth_bp
    from app.students.routes import students_bp
    from .assessments.routes import assessments_bp
    from .results.routes import results_bp
    from .analytics.routes import analytics_bp
    from .admin.routes import admin_bp
    from .setup import initialize_data

    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)

    db.init_app(app)
    login_manager.init_app(app)
    initialize_data(app)

    return app


def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        #Users
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (
                            role IN ('admin', 'class_teacher', 'subject_teacher')
                        ),
                        is_active BOOLEAN DEFAULT 1,
                        created_at TEXT)''')

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
            name TEXT NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('junior', 'senior')),
            is_common_core BOOLEAN DEFAULT 0,
            UNIQUE(name, level))
        """)

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

        # Scores table
        cursor.execute('''CREATE TABLE IF NOT EXISTS scores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        class_arm_id INTEGER NOT NULL,
                        term INTEGER NOT NULL,
                        session TEXT NOT NULL,
                        ca1_score REAL NULL DEFAULT 0,
                        ca2_score REAL NULL DEFAULT 0,
                        ca3_score REAL NULL DEFAULT 0,
                        ca4_score REAL NULL DEFAULT 0,
                        exam_score REAL NULL DEFAULT 0,
                        total_score REAL DEFAULT 0,
                        report_type TEXT NOT NULL CHECK(report_type IN ('half_term', 'full_term')),
                        created_at TEXT NOT NULL,  
                        approved INTEGER DEFAULT 0,                     
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

        cursor.execute('''CREATE TABLE IF NOT EXISTS principal_comments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            min_average REAL NOT NULL,
                            max_average REAL NOT NULL,
                            comment TEXT NOT NULL,
                            UNIQUE(min_average, max_average, comment))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS student_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                class_arm_id INTEGER NOT NULL,
                term INTEGER NOT NULL,
                session TEXT NOT NULL,
                skill_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                UNIQUE(student_id, skill_id, class_arm_id, term, session),
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (skill_id) REFERENCES skills(id)
            )''')

        skills = [
            "Coding",
            "Photography",
            "Fascinator",
            "Music",
            "Dance",
            "Maintenance and Repair",
            "Chess"
        ]

        for skill in skills:
            cursor.execute(
                "INSERT OR IGNORE INTO skills (name) VALUES (?)",
                (skill,)
            )

        comment_rows = [
            # 30–39%
            (30, 39, "This performance is well below expectation. You must take your studies more seriously."),
            (30, 39, "There is potential, but much more effort is needed. Commit to improving next term."),
            (30, 39, "You can do better. Focus, discipline, and hard work are urgently required."),
            (30, 39, "Do not give up – use this as a wake-up call to work harder and aim higher."),
            (30, 39, "Significant improvement is required. Stay determined and put in the hard work."),

            # 40–50%
            (40, 50, "This is not a true reflection of your ability. Please sit up and stay focused next term."),
            (40, 50, "You have the potential to do much better—believe in yourself and work harder next term."),
            (40, 50, "A fair attempt, but more consistency and dedication are needed. I know you can improve."),
            (40, 50, "Do not be discouraged—use this as motivation to aim higher next term. You can do it."),
            (40, 50, "Improvement is possible with better effort and time management. Stay committed and push forward."),

            # 50–60%
            (50, 60, "A satisfactory performance, but you are capable of achieving more with greater focus."),
            (50, 60, "This result shows promise—now push yourself to reach higher standards."),
            (50, 60, "You are on the right path, but stronger effort and consistency are needed."),
            (50, 60, "Average performance. Challenge yourself to improve next term."),
            (50, 60, "There is clear potential here—stay disciplined and aim for better results."),
            (50, 60, "Decent progress, but you must work harder to move beyond the basics."),

            # 60–70%
            (60, 70, "A good effort, but do not settle—keep striving for excellence."),
            (60, 70, "Solid performance, but there is room to push beyond this level."),
            (60, 70, "You are doing well—stay focused and aim even higher next term."),
            (60, 70, "A commendable result, but greater consistency will lead to stronger outcomes."),
            (60, 70, "Well done so far. Now challenge yourself to reach your full potential."),
            (60, 70, "You have built a good foundation—keep up the momentum and aim for more."),

            # 70–80%
            (70, 80, "Good work this term—now aim higher and stay consistent."),
            (70, 80, "Well done on your progress. Keep challenging yourself to go further."),
            (70, 80, "A solid result—maintain your focus and push for excellence."),
            (70, 80, "You have done well—keep up the effort and aim to improve even more."),
            (70, 80, "A commendable performance, but do not lose momentum. Stay driven."),
            (70, 80, "You are on the right path. With continued effort, even better results are within reach."),

            # 80–90%
            (80, 90, "Excellent performance—keep up the hard work and stay consistent."),
            (80, 90, "Well done! Maintain this level of focus and keep striving for excellence."),
            (80, 90, "A strong result—continue to push yourself toward the top."),
            (80, 90, "Great effort! Do not settle—aim for even greater achievement."),
            (80, 90, "You have done very well. Stay disciplined and keep progressing."),
            (80, 90, "Congratulations on your success. Now challenge yourself to reach even higher."),
        ]

        for r in comment_rows:
            cursor.execute("""
                INSERT OR IGNORE INTO principal_comments (min_average, max_average, comment)
                VALUES (?, ?, ?)
            """, r)

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
            (6, "MASTERS")
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

