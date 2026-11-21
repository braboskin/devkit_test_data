import sqlite3

db = "C:/Users/xaylpq/.devkit/devkit.db"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = con.execute(
    "select status, attempts, blocked, last_error, sanction_expires_at "
    "from ship_state where task_id = 'T-CA6FF8E2'"
).fetchall()
print(rows)
