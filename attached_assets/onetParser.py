# onet_parser.py - Extracts skill names from O*NET Skills.txt
import csv
import json

def extract_onet_skills(filepath, output_file):
    skills = set()
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            skills.add(row['Element Name'].strip())

    skills = sorted(list(skills))
    with open(output_file, 'w', encoding='utf-8') as out:
        json.dump(skills, out, indent=2)
    print(f"✅ Extracted {len(skills)} O*NET skills to {output_file}")

if __name__ == "__main__":
    extract_onet_skills("Skills.txt", "onet_skills.json")
