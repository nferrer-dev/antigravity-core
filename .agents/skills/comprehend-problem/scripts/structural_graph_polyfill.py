import ast
import json
import os
import sys

def parse_file(filepath):
    """Parse a single python file and return its imports and function definitions."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"imports": [], "functions": [], "error": "SyntaxError"}
    
    imports = []
    functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
            
    return {"imports": list(set(imports)), "functions": functions}

def build_graph(directory):
    """Build a structural dependency graph for a directory."""
    graph = {"nodes": [], "edges": []}
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                
                data = parse_file(filepath)
                if "error" in data:
                    continue
                    
                graph["nodes"].append({
                    "id": rel_path,
                    "type": "file",
                    "functions": data["functions"]
                })
                
                for imp in data["imports"]:
                    graph["edges"].append({
                        "source": rel_path,
                        "target": imp,
                        "relation": "imports"
                    })
                    
    return graph

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python structural_graph_polyfill.py <target_directory> <output_json_path>")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    output_path = sys.argv[2]
    
    print(f"Building structural graph for {target_dir}...")
    graph = build_graph(target_dir)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
        
    print(f"Success! Graph written to {output_path}")
