import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
DB_FILE = os.path.join(DB_DIR, "memory.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def insert_memory(category, content):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO memories (category, content) VALUES (?, ?)', (category, content))
    conn.commit()
    conn.close()

def get_all_memory():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT category, content FROM memories')
    rows = c.fetchall()
    conn.close()
    return [{"category": r[0], "content": r[1]} for r in rows]

def recall():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT category, content FROM memories')
    rows = c.fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]

def remember(category, content):
    insert_memory(category, content)


