"""
Script to fix JSON data by truncating strings that exceed max_length
"""
import json
from pathlib import Path

# Define max lengths for fields that are causing truncation issues
FIELD_MAX_LENGTHS = {
    'inventory.issuerequest': {
        'requested_by_username': 100,
        'requested_by_full_name': 200,
        'requested_by_mobile': 30,
        'requested_by_department': 20,
        'requested_by_section': 50,
        'status': 20,
        'approval_note': 500,
        'request_reason': 2000,
        'approved_by_section': 50,
        'approved_by_department': 20,
        'receiver_username': 100,
        'receiver_full_name': 200,
        'receiver_mobile': 30,
        'receiver_department': 20,
        'receiver_section': 50,
        'confirmed_by_department': 20,
        'confirmed_by_section': 50,
        'issued_by_department': 20,
        'issued_by_section': 50,
        'rejected_by_department': 20,
        'rejected_by_section': 50,
    },
    'inventory.returneditem': {
        'request_id': 20,
        'username': 100,
        'full_name': 200,
        'department': 20,
        'section': 50,
        'returned_by_section': 50,
        'returned_by_department': 20,
    },
    'inventory.temporaryitemhistory': {
        'request_id': 20,
        'username': 100,
        'full_name': 200,
        'department': 20,
        'section': 50,
    },
    'inventory.issuehistory': {
        'receiver_username': 100,
        'receiver_full_name': 200,
        'receiver_mobile': 30,
        'receiver_department': 20,
        'receiver_section': 50,
    },
}

def truncate_value(value, max_length):
    """Truncate string value to max_length"""
    if value is None:
        return None
    str_value = str(value)
    if len(str_value) > max_length:
        print(f"  Truncating: {str_value[:50]}... (length {len(str_value)} -> {max_length})")
        return str_value[:max_length]
    return str_value

def fix_json_file(input_file, output_file):
    """Fix JSON file by truncating strings that exceed max_length"""
    print(f"Reading {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Processing {len(data)} objects...")
    
    for obj in data:
        model = obj.get('model', '')
        if model in FIELD_MAX_LENGTHS:
            fields = obj.get('fields', {})
            max_lengths = FIELD_MAX_LENGTHS[model]
            
            for field, max_length in max_lengths.items():
                if field in fields:
                    fields[field] = truncate_value(fields[field], max_length)
    
    print(f"Writing to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Fixed JSON file created: {output_file}")

def main():
    BASE_DIR = Path(__file__).resolve().parent
    
    # Fix the filtered dump
    input_file = BASE_DIR / 'sqlite_data_dump_filtered_utf8.json'
    output_file = BASE_DIR / 'sqlite_data_dump_filtered_fixed.json'
    
    if input_file.exists():
        fix_json_file(input_file, output_file)
    else:
        print(f"File not found: {input_file}")

if __name__ == '__main__':
    main()
