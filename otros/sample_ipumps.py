import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables
load_dotenv()

# Database connection parameters
DB_PARAMS = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_random_sample(sample_size=1000):
    try:
        # Connect to the database
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get random sample using TABLESAMPLE
        # Note: TABLESAMPLE gives approximate number of rows
        query = f"""
        SELECT *
        FROM ipumps
        TABLESAMPLE BERNOULLI ({sample_size}) 
        """
        
        cur.execute(query)
        sample = cur.fetchall()
        
        print(f"Retrieved {len(sample)} random records from ipumps table")
        
        # Print first few records as example
        print("\nFirst 5 records of the sample:")
        for i, record in enumerate(sample[:5]):
            print(f"\nRecord {i + 1}:")
            print(record)
            
        return sample
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return None
        
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    sample = get_random_sample()
