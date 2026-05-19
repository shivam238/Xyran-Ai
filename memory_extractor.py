import re
from memory_db import insert_memory
from vector_memory import build_index

def extract_memory(user_input):
    text = user_input.lower().strip()
    saved = False

    # Check if it's a question - do not extract if they are asking
    is_question = any(q in text for q in ["kya", "what", "who", "?", "sakte", "batao", "bata"])

    if not is_question:
        # AGE STATEMENT
        # "meri age 19 hai", "i am 19 years old", "age is 19"
        age_match = re.search(r'(?:age|saal|umar|i am|umr)\s*(?:is|hai|of)?\s*(\d+)', text)
        if age_match:
            insert_memory("facts", f"age:{age_match.group(1)}")
            saved = True

        # NAME STATEMENT
        # "mera naam Shivam hai", "my name is Shivam", "naam Shivam hai"
        name_match = None
        
        # English: my name is X
        eng_match = re.search(r'my\s+name\s+is\s+([a-zA-Z]+)', text)
        if eng_match:
            name_match = eng_match.group(1)
            
        # Hindi: mera naam X hai / naam X hai
        if not name_match:
            hin_match = re.search(r'(?:mera\s+)?naam\s+([a-zA-Z]+)(?:\s+hai)?', text)
            if hin_match:
                potential_name = hin_match.group(1)
                blacklist = ["kya", "hai", "naam", "mera", "shuru", "band", "exit", "batao", "bata"]
                if potential_name not in blacklist:
                    name_match = potential_name

        if name_match:
            name_val = name_match.strip().capitalize()
            insert_memory("facts", f"name:{name_val}")
            saved = True

    if saved:
        build_index()
        
    return saved
