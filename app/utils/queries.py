def get_filtered_performance_base(class_arm_id, term, session, report_type):
    # Returns (cte_sql, params)
    parts = []
    params = []

    if class_arm_id:
        parts.append("x.class_arm_id = ?")
        params.append(class_arm_id)
    if term:
        parts.append("x.term = ?")
        params.append(int(term))
    if session:
        parts.append("x.session = ?")
        params.append(session)
    if report_type:
        parts.append("sc.report_type = ?")
        params.append(report_type)

    where = " AND ".join(parts) if parts else "1 = 1"

    cte = f"""
    WITH filtered_performance AS (
        SELECT
            s.id                AS student_id,
            s.full_name,
            s.gender,
            s.reg_number,
            x.class_arm_id,
            c.name || ' ' || a.arm  AS class_name,
            sc.subject_id,
            sub.name            AS subject_name,
            sub.level,
            sc.total_score,
            sc.approved,
            AVG(sc.total_score) OVER (PARTITION BY s.id) AS student_avg,   -- optional window
            sc.total_score
        FROM students s
        JOIN student_classes     x  ON s.id = x.student_id
        JOIN class_arms          a  ON x.class_arm_id = a.id
        JOIN classes             c  ON a.class_id = c.id
        JOIN scores              sc ON s.id = sc.student_id AND x.class_arm_id = sc.class_arm_id
        JOIN subjects            sub ON sc.subject_id = sub.id
        WHERE {where}
    )
    """

    return cte, params
