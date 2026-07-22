import sys
import glob
from pathlib import Path

def convert(epub_path):
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    
    book = epub.read_epub(epub_path)
    texts = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_body_content(), 'html.parser')
            texts.append(soup.get_text())
            
    out_path = Path(epub_path).with_suffix('.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(texts))
    
    print(f"Converted {Path(epub_path).name} to {out_path.name}")
    Path(epub_path).unlink()

def main():
    target_dir = Path(sys.argv[1])
    for f in target_dir.glob("*.epub"):
        try:
            convert(str(f))
        except Exception as e:
            print(f"Failed to convert {f.name}: {e}")

if __name__ == '__main__':
    main()
