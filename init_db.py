import psycopg2
import os

DB_URL = os.getenv("DATABASE_URL", "postgres://app_user:app_pass@localhost:5432/app_db")

def init_schema(schema_sql_path):
    with psycopg2.connect(DB_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur, open(schema_sql_path, "r") as f:
            sql = f.read()
            cur.execute(sql)
            print(f"Executed {schema_sql_path}")

if __name__ == "__main__":
    init_schema("migrations/001_init_mem.sql")
    init_schema("migrations/002_init_domain.sql")
