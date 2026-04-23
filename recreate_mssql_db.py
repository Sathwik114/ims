"""
Script to drop and recreate MSSQL database
"""
import pyodbc

# Connection parameters
server = '10.40.20.4,1433'
username = 'sa'
password = 'sqlsa@2012'
database = 'master'  # Connect to master to drop/create databases
target_db = 'ITIMS'

try:
    # Connect to SQL Server with autocommit enabled
    conn_str = f'DRIVER={{SQL Server Native Client 11.0}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()

    print(f"Connected to SQL Server")

    # Drop existing database if it exists
    try:
        # Kill all connections to the database first
        cursor.execute(f"ALTER DATABASE [{target_db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        cursor.execute(f"DROP DATABASE [{target_db}]")
        print(f"Database {target_db} dropped successfully")
    except pyodbc.Error as e:
        print(f"Database {target_db} might not exist or cannot be dropped: {e}")

    # Create new database
    try:
        cursor.execute(f"CREATE DATABASE [{target_db}]")
        print(f"Database {target_db} created successfully")
    except pyodbc.Error as e:
        print(f"Error creating database: {e}")

    cursor.close()
    conn.close()
    print("Database recreation completed successfully")

except Exception as e:
    print(f"Error: {e}")
