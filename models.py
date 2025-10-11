import sqlite3
import os

# DELETE the database file to start fresh
if os.path.exists('school_results.db'):
    os.remove('school_results.db')

# Create new connection
conn = sqlite3.connect('school_db.sqlite')
conn.row_factory = sqlite3.Row  # Return rows as dictionaries
cursor = conn.cursor()

# STEP 1: Create tables
cursor.executescript('''
    CREATE TABLE classes (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        level TEXT NOT NULL
    );
    
    CREATE TABLE class_arms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        arm TEXT NOT NULL,
        UNIQUE(class_id, arm),
        FOREIGN KEY (class_id) REFERENCES classes (id)
    );
''')

# STEP 2: Insert sample data
classes = [
    ("JSS 1", "JSS"),
    ("JSS 2", "JSS"),
    ("JSS 3", "JSS"),
    ("SSS 1", "SSS"),
    ("SSS 2", "SSS"),
    ("SSS 3", "SSS")
]

for name, level in classes:
    cursor.execute("INSERT INTO classes (name, level) VALUES (?, ?)", (name, level))

class_arms = [
    (1, "GOLD"), (1, "DIAMOND"),
    (2, "GOLD"), (2, "DIAMOND"),
    (3, "GOLD"), (3, "DIAMOND"),
    (4, "GOLD"), (4, "DIAMOND"),
    (5, "GOLD"), (5, "DIAMOND"),
    (6, "GOLD"), (6, "DIAMOND")
]

for class_id, arm in class_arms:
    cursor.execute("INSERT INTO class_arms (class_id, arm) VALUES (?, ?)", (class_id, arm))

conn.commit()

# STEP 3: Verify
print("=== VERIFICATION ===")
cursor.execute("SELECT * FROM classes")
print("Classes:")
for row in cursor.fetchall():
    print(dict(row))

cursor.execute("SELECT * FROM class_arms")
print("\nClass Arms:")
for row in cursor.fetchall():
    print(dict(row))

cursor.execute("""
    SELECT a.id AS arm_id, c.name AS class_name, a.arm
    FROM class_arms a
    JOIN classes c ON a.class_id = c.id
    ORDER BY c.id, a.arm
""")
print("\nJoin Result:")
for row in cursor.fetchall():
    print(dict(row))

conn.close()