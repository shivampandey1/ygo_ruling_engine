import sqlite3
import json
import os
import re

def get_card_name(card_id):
    try:
        with open(f'cards/en/{card_id}.json', 'r') as f:
            card_data = json.load(f)
            return card_data['name']
    except FileNotFoundError:
        return None

def replace_card_ids_with_names(text, card_id_to_name):
    def replace_id(match):
        card_id = match.group(1)
        return card_id_to_name.get(card_id, card_id)
    
    return re.sub(r'\b(\d+)\b', replace_id, text)

def fix_rulings(input_db, output_db):
    # Connect to the input database
    conn = sqlite3.connect(input_db)
    cursor = conn.cursor()

    # Connect to the output database (yugioh.db)
    new_conn = sqlite3.connect(output_db)
    new_cursor = new_conn.cursor()

    # Create card_id to card_name mapping
    card_id_to_name = {}
    for filename in os.listdir('cards/en'):
        if filename.endswith('.json'):
            card_id = filename[:-5]
            card_name = get_card_name(card_id)
            if card_name:
                card_id_to_name[card_id] = card_name

    # Process qa_tl table
    new_cursor.execute('''
    CREATE TABLE IF NOT EXISTS qa_tl_fixed (
        qaId INTEGER NOT NULL,
        locale TEXT NOT NULL,
        title TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        date TEXT NOT NULL,
        sourceHash INTEGER,
        translator TEXT NOT NULL,
        lastEditor TEXT NOT NULL,
        PRIMARY KEY (qaId, locale)
    )
    ''')

    cursor.execute("SELECT * FROM qa_tl")
    for row in cursor.fetchall():
        qaId, locale, title, question, answer, date, sourceHash, translator, lastEditor = row
        title = replace_card_ids_with_names(title, card_id_to_name)
        question = replace_card_ids_with_names(question, card_id_to_name)
        answer = replace_card_ids_with_names(answer, card_id_to_name)
        new_cursor.execute(
            "INSERT OR REPLACE INTO qa_tl_fixed VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qaId, locale, title, question, answer, date, sourceHash, translator, lastEditor)
        )

    # Process faq_tl_entries table
    new_cursor.execute('''
    CREATE TABLE IF NOT EXISTS faq_tl_entries_fixed (
        cardId INTEGER NOT NULL,
        locale TEXT NOT NULL,
        effect INTEGER NOT NULL,
        sourceHash INTEGER,
        content TEXT NOT NULL,
        name TEXT NOT NULL
    )
    ''')

    cursor.execute("SELECT * FROM faq_tl_entries")
    for row in cursor.fetchall():
        cardId, locale, effect, sourceHash, content = row
        card_name = card_id_to_name.get(str(cardId), "Unknown Card")
        content = replace_card_ids_with_names(content, card_id_to_name)
        new_cursor.execute(
            "INSERT OR REPLACE INTO faq_tl_entries_fixed VALUES (?, ?, ?, ?, ?, ?)",
            (cardId, locale, effect, sourceHash, content, card_name)
        )

    # Commit changes and close connections
    new_conn.commit()
    conn.close()
    new_conn.close()

    print(f"Database conversion complete. New tables added to {output_db}")

if __name__ == "__main__":
    input_db = "translations.db"
    output_db = "yugioh.db"
    fix_rulings(input_db, output_db)