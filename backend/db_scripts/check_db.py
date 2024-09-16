import sqlite3

def show_table_formats_and_entries(db_path, num_entries=5):
    # Connect to the SQLite database
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    
    # Query to get the list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Loop through the tables and print their schemas and entries
    for table in tables:
        table_name = table[0]
        print(f"Schema for table '{table_name}':")
        
        # Query to get the schema of the table
        cursor.execute(f"PRAGMA table_info({table_name});")
        schema = cursor.fetchall()
        
        # Display the schema in a readable format
        for column in schema:
            col_id, col_name, col_type, not_null, default_val, pk = column
            print(f"Column: {col_name}, Type: {col_type}, Not Null: {bool(not_null)}, Default: {default_val}, Primary Key: {bool(pk)}")
        
        print("-" * 40)
        
        # Query to get some entries from the table
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {num_entries};")
        entries = cursor.fetchall()
        
        if entries:
            print(f"Sample entries from table '{table_name}':")
            # Print column names
            column_names = [description[0] for description in cursor.description]
            print(" | ".join(column_names))
            print("-" * 40)
            
            # Print each entry
            for entry in entries:
                print(" | ".join(str(item) for item in entry))
            
            print("-" * 40)
        else:
            print(f"No entries found in table '{table_name}'.")
            print("-" * 40)
    
    # Close the connection
    cursor.close()
    connection.close()

# Replace 'db.db' with the path to your .db file
db_path = 'yugioh.db'
show_table_formats_and_entries(db_path)
