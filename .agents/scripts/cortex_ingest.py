import os
import sys
import subprocess
from pathlib import Path
import fitz  # PyMuPDF

def extract_text(file_path):
    ext = file_path.suffix.lower()
    if ext == '.pdf':
        try:
            doc = fitz.open(file_path)
            text = "\n".join(page.get_text() for page in doc)
            return text
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
            return ""
    else:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading text {file_path}: {e}")
            return ""

def ingest_directory(base_dir):
    base_path = Path(base_dir)
    save_py_path = Path.home() / ".cortex" / "save.py"
    
    if not save_py_path.exists():
        print(f"Error: save.py not found at {save_py_path}")
        return

    for root, dirs, files in os.walk(base_path):
        for file in files:
            file_path = Path(root) / file
            # the immediate subfolder under base_path is the namespace
            rel_path = file_path.relative_to(base_path)
            namespace = rel_path.parts[0] if len(rel_path.parts) > 1 else "global"
            
            content = extract_text(file_path)
            if not content.strip():
                continue
                
            print(f"Ingesting {file_path.name} into namespace '{namespace}'...")
            
            paragraphs = content.split('\n\n')
            chunks = []
            current = ""
            for p in paragraphs:
                if len(current) + len(p) > 1000 and len(current) > 0:
                    chunks.append(current.strip())
                    current = ""
                current += p + "\n\n"
            if current.strip():
                chunks.append(current.strip())
                
            print(f"  -> Sliced into {len(chunks)} chunks")
            success = 0
            for chunk in chunks:
                if not chunk.strip():
                    continue
                # Sanitize surrogates to prevent sqlite3 UnicodeEncodeError
                chunk = chunk.encode('utf-8', errors='replace').decode('utf-8')
                
                cmd = [
                    sys.executable, str(save_py_path),
                    "--type", "reference",
                    "--namespace", namespace,
                    "--importance", "1.0",
                    "--category", "foundational"
                ]
                try:
                    env = os.environ.copy()
                    env['PYTHONUTF8'] = '1'
                    subprocess.run(cmd, input=chunk.encode('utf-8'), env=env, check=True, capture_output=True)
                    success += 1
                except subprocess.CalledProcessError as e:
                    print(f"Failed to save chunk: {e.stderr.decode('utf-8', errors='ignore')}")
            
            print(f"  -> Successfully saved {success}/{len(chunks)} chunks")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cortex_ingest.py <base_directory>")
        sys.exit(1)
    ingest_directory(sys.argv[1])
