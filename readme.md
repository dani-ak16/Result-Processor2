# School Results Management & Analytics System

A web-based school results management system built with **Flask** and **SQLite**, designed to handle result uploads, assessments, reporting, and school-wide analytics for both **junior** and **senior** classes. The system features were tailored towards requirements gathered from Kembos College, Lagos, Nigeria.

The system supports:

- Subject-based result uploads (half-term & full-term)
- Automatic student averages
- Class-wide positions and senior grading
- Principal comments based on performance ranges
- Psychomotor, affective, and extracurricular skill assessments
- Admin analytics dashboard with key academic insights

---

## Features

### Result Management

- Excel-based result uploads (subject-wise)
- Upload preview with overwrite protection
- Handles students not offering specific subjects
- Automatic average calculation per student

### Assessments

- Psychomotor & affective domain grading
- Extracurricular skills (one skill per term)
- Skill score input
- Principal comments auto-filtered by average range

### Reporting

- Junior class positions (combined arms)
- Senior overall grade assignment (A+, B+, C+)
- Batch student report generation (PDF)

### Analytics Dashboard

- Best & worst performing students (school-wide)
- Class averages
- Performance by gender
- Benchmark analysis (e.g. ≥70%)
- Subject difficulty insights
- Performance distribution charts

---

## Tech Stack

- **Backend:** Flask (Python)
- **Database:** SQLite
- **Frontend:** Jinja2, HTML, CSS, JavaScript
- **Data Processing:** Pandas, OpenPyXL
- **Reporting:** ReportLab, Pillow
- **Analytics:** SQL Views & Window Functions

---
