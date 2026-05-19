from memory_db import remember

if __name__ == "__main__":
    remember("facts", "age 19")
    print("Facts saved successfully into SQLite database!")
