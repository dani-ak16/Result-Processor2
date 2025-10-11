To set up the system locally without needing an internet connection, we'll create a self-contained Flask application that can run on a local machine or school network. Here's how to implement it:

### Step 1: Set Up the Complete Application

**app.py** (Complete Version):
```python
import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, g, send_from_directory
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}
app.config['DATABASE'] = 'school_results.db'
app.config['SECRET_KEY'] = 'your_secret_key'  # For session management

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
        cursor.execute('''CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY,
                        reg_number TEXT UNIQUE NOT NULL,
                        full_name TEXT NOT NULL,
                        class TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS subjects (
                        id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS scores (
                        id INTEGER PRIMARY KEY,
                        student_id INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        score INTEGER NOT NULL,
                        term INTEGER NOT NULL,
                        year INTEGER NOT NULL,
                        FOREIGN KEY(student_id) REFERENCES students(id),
                        FOREIGN KEY(subject_id) REFERENCES subjects(id))''')
        db.commit()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def index():
    current_year = datetime.now().year
    return render_template('upload.html', current_year=current_year)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['file']
    subject = request.form['subject']
    term = request.form['term']
    year = request.form['year']
    
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        errors, success_count = process_upload(filepath, subject, term, year)
        
        if errors:
            return render_template('upload_error.html', 
                                  errors=errors, 
                                  success_count=success_count)
        
        return render_template('upload_success.html', 
                              success_count=success_count)
    
    return redirect(url_for('index'))

def process_upload(filepath, subject_name, term, year):
    errors = []
    success_count = 0
    db = get_db()
    
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Normalize column names
        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        
        required_cols = {'reg_number', 'full_name', 'class', 'score'}
        missing_cols = required_cols - set(df.columns)
        
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            errors.append(f"Found columns: {', '.join(df.columns)}")
            return errors, success_count
        
        cursor = db.cursor()
        
        # Insert subject
        cursor.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (subject_name,))
        subject_row = cursor.execute("SELECT id FROM subjects WHERE name = ?", 
                                   (subject_name,)).fetchone()
        subject_id = subject_row['id'] if subject_row else None
        
        if not subject_id:
            errors.append(f"Failed to get subject ID for {subject_name}")
            return errors, success_count
        
        for _, row in df.iterrows():
            try:
                # Handle potential NaN values
                score_val = row['score']
                if pd.isna(score_val):
                    errors.append(f"Missing score for {row['full_name']}")
                    continue
                    
                score = float(score_val)
                if not (0 <= score <= 100):
                    errors.append(f"Invalid score for {row['full_name']}: {score}")
                    continue
                
                # Insert student if new
                cursor.execute('''INSERT OR IGNORE INTO students 
                              (reg_number, full_name, class) 
                              VALUES (?, ?, ?)''',
                              (row['reg_number'], row['full_name'], row['class']))
                
                # Get student ID
                student_row = cursor.execute("SELECT id FROM students WHERE reg_number = ?", 
                                          (row['reg_number'],)).fetchone()
                student_id = student_row['id'] if student_row else None
                
                if not student_id:
                    errors.append(f"Failed to get student ID for {row['full_name']}")
                    continue
                
                # Insert score
                cursor.execute('''INSERT INTO scores 
                              (student_id, subject_id, score, term, year) 
                              VALUES (?, ?, ?, ?, ?)''',
                              (student_id, subject_id, score, term, year))
                
                success_count += 1
            except Exception as e:
                errors.append(f"Error processing {row['full_name']}: {str(e)}")
        
        db.commit()
        
    except Exception as e:
        errors.append(f"File processing error: {str(e)}")
    
    return errors, success_count

@app.route('/students')
def view_students():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    return render_template('students.html', students=students)

@app.route('/results')
def view_results():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT students.reg_number, students.full_name, students.class, 
               subjects.name, scores.score, scores.term, scores.year
        FROM scores
        JOIN students ON scores.student_id = students.id
        JOIN subjects ON scores.subject_id = subjects.id
        ORDER BY scores.year DESC, scores.term DESC, students.class, students.full_name
    ''')
    results = cursor.fetchall()
    return render_template('results.html', results=results)

@app.route('/student-report')
def student_report():
    reg_number = request.args.get('reg_number')
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)
    
    if not reg_number or term is None or year is None:
        current_year = datetime.now().year
        return render_template('report_form.html', current_year=current_year)
    
    db = get_db()
    cursor = db.cursor()
    
    # Get student bio data
    cursor.execute("SELECT * FROM students WHERE reg_number = ?", (reg_number,))
    student = cursor.fetchone()
    
    if not student:
        return render_template('error.html', message="Student not found")
    
    # Get all scores for the student in the specified term/year
    cursor.execute('''
        SELECT subjects.name, scores.score
        FROM scores
        JOIN subjects ON scores.subject_id = subjects.id
        WHERE scores.student_id = ? 
        AND scores.term = ? 
        AND scores.year = ?
    ''', (student['id'], term, year))
    scores = cursor.fetchall()
    
    if not scores:
        return render_template('error.html', message="No results found for this term/year")
    
    # Calculate total and average
    total = sum(score['score'] for score in scores)
    average = total / len(scores) if scores else 0
    
    return render_template('student_report.html', 
                           student=student,
                           scores=scores,
                           term=term,
                           year=year,
                           average=average,
                           current_date=datetime.now().strftime('%Y-%m-%d'))

# Home page
@app.route('/home')
def home():
    return render_template('home.html')

# Static files (CSS, JS)
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
```

### Step 2: Create Templates Directory

Create a `templates` directory with these files:

1. **templates/home.html** (Main Navigation Page):
```html
<!DOCTYPE html>
<html>
<head>
    <title>School Result System</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <h1>School Result Processing System</h1>
        <div class="menu">
            <a href="/" class="btn">Upload Results</a>
            <a href="/students" class="btn">View Students</a>
            <a href="/results" class="btn">View All Results</a>
            <a href="/student-report" class="btn">Generate Student Report</a>
        </div>
        <div class="instructions">
            <h2>How to Use:</h2>
            <ol>
                <li>Subject teachers upload their results using the "Upload Results" option</li>
                <li>Class teachers can view all students and their results</li>
                <li>Generate individual student reports with the "Generate Student Report" option</li>
                <li>All data is stored in a central database on this computer</li>
            </ol>
            <p><strong>Note:</strong> This system runs entirely on this computer. No internet connection is required.</p>
        </div>
    </div>
</body>
</html>
```

2. **templates/upload.html**, **templates/upload_success.html**, **templates/upload_error.html** (Same as before)

3. **templates/students.html**, **templates/results.html** (Same as before)

4. **templates/report_form.html**, **templates/student_report.html** (Same as before)

5. **templates/error.html**:
```html
<!DOCTYPE html>
<html>
<head>
    <title>Error</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <h1>Error</h1>
        <p>{{ message }}</p>
        <a href="/home">Return to Home</a>
    </div>
</body>
</html>
```

### Step 3: Create Static Directory (for CSS)

Create a `static` directory with:

**static/style.css**:
```css
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    background-color: #f5f5f5;
}

.container {
    background: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

h1, h2, h3 {
    color: #2c3e50;
}

.btn {
    display: inline-block;
    background: #3498db;
    color: white;
    padding: 12px 24px;
    margin: 10px;
    border-radius: 4px;
    text-decoration: none;
    font-weight: bold;
    transition: background 0.3s;
}

.btn:hover {
    background: #2980b9;
}

.menu {
    text-align: center;
    margin: 30px 0;
}

form {
    background: #f9f9f9;
    padding: 20px;
    border-radius: 8px;
    margin-top: 20px;
}

.form-group {
    margin-bottom: 15px;
}

label {
    display: block;
    margin-bottom: 5px;
    font-weight: bold;
}

input[type="text"],
input[type="number"],
select {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 16px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
}

th, td {
    border: 1px solid #ddd;
    padding: 12px;
    text-align: left;
}

th {
    background-color: #f2f2f2;
    font-weight: bold;
}

tr:nth-child(even) {
    background-color: #f9f9f9;
}

.instructions {
    background: #e8f4fc;
    padding: 20px;
    border-radius: 8px;
    margin-top: 30px;
}

.instructions ol {
    padding-left: 20px;
}

.signature {
    display: inline-block;
    width: 200px;
    border-top: 1px solid #000;
    margin-top: 40px;
}

@media print {
    .no-print {
        display: none;
    }
    
    body {
        padding: 0;
        background: white;
    }
    
    .container {
        box-shadow: none;
        padding: 0;
    }
}
```

### Step 4: Create a Batch File to Launch the Application

Create a file named `Start Server.bat` (Windows) or `start_server.sh` (Mac/Linux):

**For Windows (Start Server.bat)**:
```batch
@echo off
echo Starting School Result System...
python app.py
pause
```

**For Mac/Linux (start_server.sh)**:
```bash
#!/bin/bash
echo "Starting School Result System..."
python3 app.py
```

### Step 5: Final Directory Structure

```
School Result System/
├── app.py
├── Start Server.bat       # Windows launch script
├── start_server.sh        # Mac/Linux launch script
├── school_results.db      # Database (created on first run)
├── uploads/               # Temporary storage for uploaded files
├── static/
│   └── style.css          # CSS styles
└── templates/
    ├── home.html          # Main navigation
    ├── upload.html        # Upload form
    ├── upload_success.html
    ├── upload_error.html
    ├── students.html      # Student list
    ├── results.html       # All results
    ├── report_form.html   # Report request form
    ├── student_report.html # Individual report
    └── error.html         # Error page
```

### Step 6: Installation and Usage Instructions

1. **Install Python**:
   - Download and install Python 3.9+ from [python.org](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"

2. **Install Required Packages**:
   - Open Command Prompt or Terminal in the project folder
   - Run: `pip install flask pandas openpyxl`

3. **Start the Application**:
   - Double-click `Start Server.bat` (Windows) or run `./start_server.sh` (Mac/Linux)
   - The server will start and display: `Running on http://0.0.0.0:5000/`

4. **Access the System**:
   - On the server computer: Open browser to `http://localhost:5000/home`
   - On other computers in the same network: Use `http://<server_ip>:5000/home`
     (Find server IP with `ipconfig` on Windows or `ifconfig` on Mac/Linux)

5. **Teacher Workflow**:
   - Subject teachers visit the URL and click "Upload Results"
   - They select their subject, term, year, and upload their spreadsheet
   - After all teachers upload, class teachers can generate reports

### Key Features for Offline Use:

1. **Self-Contained System**:
   - All data stored in a single SQLite database file
   - No external services or internet required

2. **Central Database**:
   - All uploads update the central database on the server computer
   - Reports are generated from this central database

3. **Network Access**:
   - The server runs on port 5000 and is accessible to all computers on the same local network
   - Teachers can access the system from their own computers

4. **Easy Launch**:
   - Simple batch/script files to start the server
   - No complex installation required

5. **Data Security**:
   - All data stays within the school network
   - Regular backups can be made by copying the database file

### Backup and Maintenance:

1. **Regular Backups**:
   - Manually copy the `school_results.db` file to a safe location
   - Set up a script to automatically back up daily

2. **Updating the System**:
   - To update, replace the Python files while preserving the database
   - Add new features by modifying the code

3. **Troubleshooting**:
   - Check the command window for error messages
   - Ensure no other program is using port 5000
   - Make sure all computers are on the same network

This setup creates a fully functional, offline result processing system that can run on any Windows, Mac, or Linux computer. Teachers can upload results from their own computers, and all data is consolidated in a central database on the server machine.