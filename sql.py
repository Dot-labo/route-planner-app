import sqlite3

# === SQLite データベース初期化 ===
conn = sqlite3.connect("locations.db")
c = conn.cursor()

# 既存テーブルがなければ作成（初回）
c.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        name TEXT PRIMARY KEY,
        address TEXT NOT NULL,
        route TEXT
    )
""")

# 既存テーブルに route 列がない場合に追加（2回目以降の実行対策）
try:
    c.execute("ALTER TABLE locations ADD COLUMN route TEXT")
except sqlite3.OperationalError:
    pass  # 既に追加済みなら無視

conn.commit()

