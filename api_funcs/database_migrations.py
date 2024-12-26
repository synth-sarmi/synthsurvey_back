import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# SQL script to modify the database structure
MIGRATION_SQL = """
-- Drop the survey_questions table as it's no longer needed
DROP TABLE IF EXISTS survey_questions;

-- Drop the existing surveys table
DROP TABLE IF EXISTS surveys CASCADE;

-- Create the new surveys table with URL-based structure
CREATE TABLE surveys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    audience_id INTEGER REFERENCES audiences(id),
    url VARCHAR(2048) NOT NULL,
    url_type VARCHAR(50) NOT NULL, -- e.g., 'form', 'website', 'survey'
    status VARCHAR(50) NOT NULL DEFAULT 'Not Processed', -- 'Not Processed', 'Processing', 'Completed', 'Failed'
    responses_generated INTEGER DEFAULT 0,
    total_responses INTEGER DEFAULT 0, -- Will be set to audience size when created
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX idx_surveys_user_id ON surveys(user_id);
CREATE INDEX idx_surveys_audience_id ON surveys(audience_id);

-- Create trigger for updated_at column
CREATE TRIGGER update_surveys_updated_at
    BEFORE UPDATE ON surveys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""

def run_migration():
    """
    Executes the database migration using environment variables for connection.
    """
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Execute the migration script
        cur.execute(MIGRATION_SQL)
        
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"An error occurred during migration: {e}")
        
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    load_dotenv()
    run_migration()
