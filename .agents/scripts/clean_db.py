import sqlite3
from pathlib import Path

db_path = Path.home() / ".cortex" / "cortex.db"
conn = sqlite3.connect(str(db_path))
c = conn.cursor()
c.execute("DELETE FROM memories WHERE category = 'textbook'")
conn.commit()
print(f"Deleted {c.rowcount} textbook chunks to prepare for clean reingestion.")
conn.close()
