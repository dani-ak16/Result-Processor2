from flask import render_template, request, redirect, url_for
from utils.decorators import login_required, roles_required
from extensions import db
from . import admin_bp


@admin_bp.route("/dashboard", methods=["GET"])
@login_required
@roles_required("admin")
def admin_dashboard():
    db = get_db()
    cursor = db.cursor()

    # Get filter parameters (all optional)
    class_arm_id = request.args.get("class_arm_id")
    term = request.args.get("term")
    session = request.args.get("session")
    report_type = request.args.get("report_type", "full_term")

    cte, params = get_filtered_performance_base(class_arm_id, term, session, report_type)

    # Fetch all class arms for dropdown/filter
    classes = cursor.execute("""
        SELECT a.id as arm_id, c.name as class_name, a.arm
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        ORDER BY c.id, a.arm
    """).fetchall()

    # Common base filters (for student_classes)
    base_filters = []
    base_params = []
    if class_arm_id:
        base_filters.append("x.class_arm_id = ?")
        base_params.append(class_arm_id)
    if term:
        base_filters.append("x.term = ?")
        base_params.append(term)
    if session:
        base_filters.append("x.session = ?")
        base_params.append(session)

    base_where = " AND ".join(base_filters) if base_filters else "1=1"
    base_params_list = base_params[:]  # copy

    # For queries that need report_type (all scores-based queries)
    report_where = f"sc.report_type = ?" if report_type else "1=1"
    report_params = [report_type] if report_type else []

    # 1. Student performance query
    student_query = f"""
        SELECT 
            s.id, s.full_name, s.reg_number, s.gender,
            c.name || ' ' || a.arm AS class_name,
            AVG(sc.total_score) AS average,
            SUM(CASE WHEN sc.approved = 1 THEN 1 ELSE 0 END) AS approved_count,
            COUNT(sc.id) AS subject_count
        FROM students s
        JOIN scores sc ON s.id = sc.student_id
        JOIN student_classes x ON s.id = x.student_id AND sc.class_arm_id = x.class_arm_id
        JOIN class_arms a ON x.class_arm_id = a.id
        JOIN classes c ON a.class_id = c.id
        WHERE {base_where} AND {report_where}
        GROUP BY s.id
        HAVING subject_count > 0
        ORDER BY average DESC
    """
    students = cursor.execute(student_query, base_params_list + report_params).fetchall()

    # 2. Class averages
    class_avg_query = f"""
        SELECT 
            c.name || ' ' || a.arm AS class_name,
            COUNT(DISTINCT x.student_id) AS student_count,
            AVG(sc.total_score) AS class_average
        FROM class_arms a
        JOIN classes c ON a.class_id = c.id
        JOIN student_classes x ON a.id = x.class_arm_id
        JOIN scores sc ON x.student_id = sc.student_id AND x.class_arm_id = sc.class_arm_id
        WHERE {base_where} AND {report_where}
        GROUP BY a.id, c.name, a.arm
        ORDER BY class_average DESC
    """
    class_averages = cursor.execute(class_avg_query, base_params_list + report_params).fetchall()

    # 3. Gender performance
    gender_query = f"""
        SELECT 
            s.gender,
            AVG(sc.total_score) AS avg_score,
            COUNT(DISTINCT s.id) AS student_count
        FROM students s
        JOIN scores sc ON s.id = sc.student_id
        JOIN student_classes x ON s.id = x.student_id AND sc.class_arm_id = x.class_arm_id
        WHERE {base_where} AND {report_where}
        GROUP BY s.gender
        ORDER BY avg_score DESC
    """
    gender_performance = cursor.execute(gender_query, base_params_list + report_params).fetchall()

    
    # 4. Overall stats (using the fixed CTE version from previous response)
    # overall_query = f"""
    # WITH student_averages AS (
    #     SELECT 
    #         s.id,
    #         AVG(sc.total_score) AS avg_score
    #     FROM students s
    #     JOIN scores sc ON s.id = sc.student_id
    #     JOIN student_classes x ON s.id = x.student_id AND sc.class_arm_id = x.class_arm_id
    #     WHERE {base_where} AND {report_where}
    #     GROUP BY s.id
    #     HAVING COUNT(sc.id) > 0
    # )
    # SELECT 
    #     COUNT(*) AS total_students,
    #     AVG(avg_score) AS school_average,
    #     SUM(CASE WHEN avg_score >= 70 THEN 1 ELSE 0 END) AS above_70,
    #     SUM(CASE WHEN avg_score < 70 THEN 1 ELSE 0 END) AS below_70,
    #     (SELECT COUNT(*) FROM scores sc WHERE {base_where} AND sc.report_type = ? AND sc.approved = 1) AS approved_scores,
    #     (SELECT COUNT(*) FROM scores sc WHERE {base_where} AND sc.report_type = ?) AS total_scores
    # FROM student_averages;
    # """
    overall = cursor.execute(f"""
        {cte}
        SELECT
            COUNT(DISTINCT student_id)                  AS total_students,
            AVG(student_avg)                            AS school_average,
            SUM(CASE WHEN student_avg >= 70 THEN 1 ELSE 0 END) AS above_70,
            SUM(CASE WHEN student_avg <  70 THEN 1 ELSE 0 END) AS below_70
        FROM filtered_performance
        """, params).fetchone()

    # 5. Prepare chart data
    # Top 10 students (for bar/line chart)
    top_students_data = {
        "labels": [s["full_name"] for s in students[:10]],
        "values": [round(s["average"], 2) for s in students[:10]]
    }

    # Class averages chart data
    class_avg_data = {
        "labels": [row["class_name"] for row in class_averages],
        "values": [round(row["class_average"], 2) for row in class_averages],
        "counts": [row["student_count"] for row in class_averages]  # optional for tooltip
    }

    # Benchmark distribution (for pie/donut chart)
    benchmark_data = {
        "labels": ["Above 70%", "Below 70%"],
        "values": [overall["above_70"], overall["below_70"]]
    } if overall else {"labels": [], "values": []}

    return render_template(
        "admin_dashboard.html",
        classes=classes,                    # for dropdown
        students=students,                  # full list or paginated
        class_averages=class_averages,      # table of class averages
        overall_stats=overall,        # KPIs: total students, school avg, etc.
        gender_performance=gender_performance,
        term=term,
        session=session,
        report_type=report_type,
        # Chart data (pass to JavaScript, e.g., Chart.js)
        top_students_data=top_students_data,
        class_avg_data=class_avg_data,
        benchmark_data=benchmark_data,
        # Optional: add more chart data here
    )

@admin_bp.route("/students")
def admin_students():
    db = get_db()
    cursor = db.cursor()
    
    search = request.args.get("search", "")
    
    if search:
        cursor.execute("""
            SELECT s.*, d.name AS dept_name
            FROM students s
            LEFT JOIN departments d ON d.id = s.department_id
            WHERE s.full_name LIKE ? OR s.reg_number LIKE ?
            ORDER BY s.full_name
        """, (f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
            SELECT s.*, d.name AS dept_name
            FROM students s
            LEFT JOIN departments d ON d.id = s.department_id
            ORDER BY s.full_name
        """)
    
    students = cursor.fetchall()
    
    return render_template("admin/students_list.j2", students=students, search=search)

@admin_bp.route("/student/<int:student_id>/edit")
def edit_student(student_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT * FROM students WHERE id=?
    """, (student_id,))
    student = cursor.fetchone()
    
    cursor.execute("SELECT id, name FROM departments")
    departments = cursor.fetchall()
    
    return render_template("admin/edit_student.j2",
                           student=student,
                           departments=departments)

@admin_bp.route("/student/<int:student_id>/update", methods=["POST"])
def update_student(student_id):
    db = get_db()
    cursor = db.cursor()
    
    full_name = request.form.get("full_name").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    department_id = request.form.get("department_id")
    photo = request.files.get("photo")
    
    # Update photo if uploaded
    photo_filename = None
    if photo and photo.filename:
        from PIL import Image, ExifTags
        import io, base64, os
        from werkzeug.utils import secure_filename
        
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], "photos")
        os.makedirs(upload_dir, exist_ok=True)
        
        ext = photo.filename.rsplit(".", 1)[-1].lower()
        saved_name = secure_filename(f"student_{student_id}.{ext}")
        saved_path = os.path.join(upload_dir, saved_name)
        photo.save(saved_path)
        
        # Compress
        compressed_name = f"compressed_{saved_name}"
        compressed_path = os.path.join(upload_dir, compressed_name)
        compress_image(saved_path, compressed_path)
        
        photo_filename = compressed_name
    
    # Update DB
    if photo_filename:
        cursor.execute("""
            UPDATE students
            SET full_name=?, age=?, gender=?, department_id=?, photo=?
            WHERE id=?
        """, (full_name, age, gender, department_id, photo_filename, student_id))
    else:
        cursor.execute("""
            UPDATE students
            SET full_name=?, age=?, gender=?, department_id=?
            WHERE id=?
        """, (full_name, age, gender, department_id, student_id))
    
    db.commit()
    
    return redirect(url_for("admin_students"))
