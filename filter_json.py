"""
Script to filter out specific models from JSON file
"""
import json
from pathlib import Path

def filter_json_file(input_file, output_file, exclude_models):
    """Filter out specific models from JSON file"""
    print(f"Reading {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Processing {len(data)} objects...")
    
    # Filter out excluded models
    filtered_data = [obj for obj in data if obj.get('model') not in exclude_models]
    
    print(f"Filtered to {len(filtered_data)} objects (removed {len(data) - len(filtered_data)} objects)")
    
    print(f"Writing to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, indent=2)
    
    print(f"Filtered JSON file created: {output_file}")

def main():
    BASE_DIR = Path(__file__).resolve().parent
    
    # Filter out Django built-in models and problematic inventory models from the full dump
    input_file = BASE_DIR / 'sqlite_data_dump_utf8.json'
    output_file = BASE_DIR / 'sqlite_data_dump_filtered.json'
    exclude_models = [
        # Django built-in models (already created by migrations)
        'auth.permission',
        'auth.group',
        'auth.user',
        'contenttypes.contenttype',
        'sessions.session',
        'admin.logentry',
        # Problematic inventory models
        'inventory.temporaryitemhistory',
        'inventory.issuerequest',
    ]
    
    if input_file.exists():
        filter_json_file(input_file, output_file, exclude_models)
    else:
        print(f"File not found: {input_file}")

if __name__ == '__main__':
    main()
