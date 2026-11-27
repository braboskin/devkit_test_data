import sqlite3, pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.secrets\atlas.db")
print("db exists:", p.exists())
con = sqlite3.connect(p)
cur = con.cursor()
tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
print("tables:", [t for t in tables if "event" in t.lower()])
for t in [t for t in tables if "event" in t.lower()]:
    print(t, "rows:", cur.execute(f"select count(*) from {t}").fetchone()[0])
    for row in cur.execute(f"select * from {t} limit 3"):
        print(row)
