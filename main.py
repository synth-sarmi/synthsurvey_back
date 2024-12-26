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
    allow_origins=[
        "http://synthsurvey.com",
        "https://synthsurvey.com",
        "http://www.synthsurvey.com",
        "https://www.synthsurvey.com",
        "http://localhost:3000",  # For local development
        "http://localhost:5000",  # For local development
        "http://localhost:4173"   # For local development
    ],
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
        # Create waitlist table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
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
