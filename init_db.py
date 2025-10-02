import psycopg2

def init_db():
    MEMORY_SCHEMA_SQL = open("migrations/001_init_mem.sql").read()
    conn = psycopg2.connect("dbname=dbname user=user password=password host=localhost port=5432")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(MEMORY_SCHEMA_SQL)
    cur.close()
    conn.close()
    print("Database initialized!")



def init_memory_db():
    MEMORY_SCHEMA_SQL = open("migrations/002_init_mem.sql").read()
    conn = psycopg2.connect("dbname=dbname user=user password=password host=localhost port=5433")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(MEMORY_SCHEMA_SQL)
    cur.close()
    conn.close()
    print("Memory initialized!")

if __name__ == "__main__":
    init_db()
    init_memory_db()
