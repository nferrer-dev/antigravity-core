import sqlite3
c = sqlite3.connect(r'C:\Users\nferr\.cortex\cortex.db')
res = c.execute("SELECT namespace, content FROM memories WHERE namespace='technical-debate' LIMIT 1").fetchone()
print(f"Namespace: {res[0]}")
print(f"Content Preview:\n{res[1][:500]}...")
