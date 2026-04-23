"""
Script to convert JSON file from UTF-16 to UTF-8
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
json_file = BASE_DIR / 'sqlite_data_dump.json'

# Read with UTF-16 (with BOM detection)
try:
    with open(json_file, 'r', encoding='utf-16') as f:
        content = f.read()
    
    # Write with UTF-8
    output_file = BASE_DIR / 'sqlite_data_dump_utf8.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"File converted to UTF-8: {output_file}")
except Exception as e:
    print(f"Error: {e}")
    print("Trying alternative method...")
    
    # Try with encoding detection
    import chardet
    with open(json_file, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
        print(f"Detected encoding: {encoding}")
    
    with open(json_file, 'r', encoding=encoding) as f:
        content = f.read()
    
    output_file = BASE_DIR / 'sqlite_data_dump_utf8.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"File converted to UTF-8: {output_file}")
