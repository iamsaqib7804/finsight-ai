from db import init_db, query_one, query_all

init_db()

row = query_one("SELECT COUNT(*) AS cnt FROM users")
print(f"✅ Connected to MySQL. Users: {row['cnt']}")

tables = query_all("SHOW TABLES")
print("📋 Tables:")
for t in tables:
    print("   -", list(t.values())[0])