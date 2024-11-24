import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# SQL script to create the database structure
CREATE_TABLES = """
-- Users table to store additional user info beyond Auth0
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    auth0_id VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    tokens_remaining INTEGER DEFAULT 0,
    subscription_tier VARCHAR(50) DEFAULT 'free'
);

-- Tokens table to track token purchases and usage
CREATE TABLE tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    amount INTEGER NOT NULL,
    transaction_type VARCHAR(20) NOT NULL, -- 'purchase' or 'usage'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    CONSTRAINT positive_amount CHECK (amount > 0)
);

-- Audiences table to store target demographics
CREATE TABLE audiences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    size INTEGER NOT NULL,
    demographics JSONB, -- Flexible storage for demographic criteria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT positive_size CHECK (size > 0)
);

-- Questions table to store survey questions
CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    question_type VARCHAR(50) NOT NULL, -- 'multiple_choice', 'open_ended', etc.
    options JSONB, -- For multiple choice questions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Surveys table to combine questions and audiences
CREATE TABLE surveys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    audience_id INTEGER REFERENCES audiences(id),
    status VARCHAR(50) NOT NULL DEFAULT 'draft', -- 'draft', 'active', 'completed'
    token_cost INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT positive_token_cost CHECK (token_cost > 0)
);

-- Survey questions junction table
CREATE TABLE survey_questions (
    survey_id INTEGER REFERENCES surveys(id),
    question_id INTEGER REFERENCES questions(id),
    order_number INTEGER NOT NULL,
    PRIMARY KEY (survey_id, question_id)
);

-- Results table to store survey responses
CREATE TABLE results (
    id SERIAL PRIMARY KEY,
    survey_id INTEGER REFERENCES surveys(id),
    response_data JSONB NOT NULL, -- Stores all responses in a flexible format
    respondent_demographics JSONB, -- Demographic info of respondent
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    validation_score FLOAT -- AI-generated score for response quality
);

-- Create indexes for better query performance
CREATE INDEX idx_users_auth0_id ON users(auth0_id);
CREATE INDEX idx_tokens_user_id ON tokens(user_id);
CREATE INDEX idx_audiences_user_id ON audiences(user_id);
CREATE INDEX idx_questions_user_id ON questions(user_id);
CREATE INDEX idx_surveys_user_id ON surveys(user_id);
CREATE INDEX idx_results_survey_id ON results(survey_id);

-- Create a function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_audiences_updated_at
    BEFORE UPDATE ON audiences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_questions_updated_at
    BEFORE UPDATE ON questions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_surveys_updated_at
    BEFORE UPDATE ON surveys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""

def setup_database():
    """
    Creates the database structure using environment variables for connection.
    
    Required environment variables:
    - DB_HOST
    - DB_PORT
    - DB_NAME
    - DB_USER
    - DB_PASSWORD
    """
    try:
        # Connect to PostgreSQL and create tables
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Execute the table creation script
        cur.execute(CREATE_TABLES)
        
        print("Database tables created successfully!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    load_dotenv()
    setup_database()
