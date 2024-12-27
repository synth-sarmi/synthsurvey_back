import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from api_funcs.active_routes import router as active_router
from api_funcs.inactive_routes import router as inactive_router

# Load environment variables
load_dotenv()

app = FastAPI(title="SynthSurvey API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins during development
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include routers
app.include_router(active_router, tags=["active"])
app.include_router(inactive_router, tags=["inactive"])

# Initialize database tables
def init_db():
    from api_funcs.active_routes import DB_PARAMS
    import psycopg2
    
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    try:
        # Create updated_at trigger function if it doesn't exist
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)

        # Create waitlist table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create users table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                auth0_id VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create audiences table with unique name constraint
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audiences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                size INTEGER NOT NULL,
                demographics JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            );
        """)

        # Create trigger for audiences updated_at
        cur.execute("""
            DROP TRIGGER IF EXISTS update_audiences_updated_at ON audiences;
            CREATE TRIGGER update_audiences_updated_at
                BEFORE UPDATE ON audiences
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
