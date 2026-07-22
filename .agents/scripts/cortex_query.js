const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const args = process.argv.slice(2);
let workflow = null;
let text = null;
for (const arg of args) {
    if (arg.startsWith('--workflow=')) {
        workflow = arg.split('=')[1];
    } else {
        text = arg;
    }
}

if (!workflow || !['validate-design', 'technical-debate', 'iterative-implement'].includes(workflow)) {
    console.error('Error: --workflow parameter is required and must be one of: validate-design, technical-debate, iterative-implement');
    process.exit(1);
}
if (!text) {
    console.error('Error: Search query is required.');
    process.exit(1);
}

const pyScript = `
import sqlite3
import sys
from pathlib import Path

db_path = Path.home() / '.cortex' / 'cortex.db'
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
query = sys.argv[1]
namespace = sys.argv[2]

# Perform a simple keyword-based fallback search for the librarian
search_term = f"%{query}%"
res = cur.execute("SELECT content FROM memories WHERE namespace=? AND content LIKE ? LIMIT 5", (namespace, search_term)).fetchall()

# If keyword search is too strict, split into tokens and search
if not res:
    tokens = query.split()
    if tokens:
        like_clauses = " AND ".join(["content LIKE ?"] * len(tokens))
        params = [namespace] + [f"%{t}%" for t in tokens]
        res = cur.execute(f"SELECT content FROM memories WHERE namespace=? AND {like_clauses} LIMIT 5", params).fetchall()

for i, r in enumerate(res):
    print(f"[Result {i+1}]:")
    # Truncate if massive
    content = r[0]
    if len(content) > 1000:
        content = content[:1000] + "..."
    print(content)
    print("---")
`;

const tempPy = path.join(os.tmpdir(), 'cortex_fallback_query.py');
fs.writeFileSync(tempPy, pyScript);

try {
    const output = execSync(`python "${tempPy}" "${text}" "${workflow}"`, { encoding: 'utf8' });
    console.log(output);
} catch (err) {
    console.error('Query failed:', err.message);
    process.exit(1);
}
