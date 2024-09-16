import requests
import pandas as pd
import random
from tabulate import tabulate
from sqlalchemy import create_engine, text
import sqlite3
import json


'''
list of things we need (because they could be relevant to rulings):
name
humanReadableCardType
desc
race
atk
def
level (note: linkval/rank/level should be used to populate a singular level/rank/linkrating fiend)
attribute
rank
card_images
'''

def create_card_dataframe(api_response):
    # Extract card data from the response
    cards_data = api_response['data']
    
    # List to store processed card data
    processed_cards = []
    
    for card in cards_data:
        # Extract required fields, using get() to handle missing keys
        processed_card = {
            'name': card.get('name', ''),
            #'id': card.get('id', ''), #problem: ygoorg and ygoprodeck use different ids
            'humanReadableCardType': card.get('humanReadableCardType', ''),
            'desc': card.get('desc', ''),
            'race': card.get('race', ''),
            'atk': card.get('atk', None),
            'def': card.get('def', None),
            'attribute': card.get('attribute', ''),
            'card_images': card.get('card_images', [{}])[0]  # Store first image dict
        }
        
        # Handle level/rank/linkval
        processed_card['level'] = card.get('level') or card.get('rank') or card.get('linkval')
        
        processed_cards.append(processed_card)
    
    # Create DataFrame
    df = pd.DataFrame(processed_cards)
    
    # Print 5 random rows
    # print("Sample of 5 random cards:")
    # print(tabulate(df.sample(n=5, random_state=42), headers='keys', tablefmt='psql', showindex=False))
    
    return df

def create_sqlite_database(df, db_name='cards.db'): #master db is yugioh.db, don't overwrite it
    # Convert card_images column to JSON string
    df['card_images'] = df['card_images'].apply(json.dumps)
    
    # Create a connection to the SQLite database
    conn = sqlite3.connect(db_name)
    
    # Write the DataFrame to SQLite
    df.to_sql('cards', conn, if_exists='replace', index=False)
    
    print(f"Database '{db_name}' created successfully.")
    
    # Verify the data by querying the database
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards LIMIT 5")
    result = cursor.fetchall()
    print("\nSample data from the database:")
    print(tabulate(result, headers=df.columns, tablefmt='psql'))
    
    # Close the connection
    conn.close()


# Main
api_url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
response = requests.get(api_url)
if response.status_code == 200:
    print("Retrieved data successfully")
    card_df = create_card_dataframe(response.json())
    create_sqlite_database(card_df)
else:
    print(f"Failed to retrieve data: {response.status_code}")
