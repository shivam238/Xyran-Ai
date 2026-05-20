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


def migrate_old_neural_memories():
    import json
    neural_file = os.path.join(DB_DIR, "neural_memory.json")
    migrated_flag = os.path.join(DB_DIR, ".migrated")
    
    if os.path.exists(migrated_flag):
        return
        
    if not os.path.exists(neural_file):
        return
        
    try:
        with open(neural_file, "r") as f:
            data = json.load(f)
        
        if not data:
            with open(migrated_flag, "w") as f:
                f.write("done")
            return
            
        init_db()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        for item in data:
            if isinstance(item, dict) and "text" in item:
                text = item["text"].strip()
                if text:
                    c.execute('INSERT INTO memories (category, content) VALUES (?, ?)', ("conversations", text))
                    
        conn.commit()
        conn.close()
        
        with open(migrated_flag, "w") as f:
            f.write("done")
        print(">>> Dynamic Migration: Imported old neural memories into SQLite memory database! ✅")
    except Exception as e:
        print(f"Warning: Failed to migrate old neural memories: {e}")



