from flask import render_template, request, redirect, url_for
from . import downloads_bp
from extensions import db

@downloads_bp.route('/student-template')
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

@downloads_bp.route('/result-template')
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
        'full_name': [s['full_name'] for s in students],
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
