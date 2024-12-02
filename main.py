import os
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import jwt
import httpx
from functools import lru_cache
from dotenv import load_dotenv
import random
import requests
from jwt.exceptions import PyJWTError, ExpiredSignatureError, InvalidTokenError
import json

# Load environment variables
load_dotenv()

app = FastAPI(title="SynthSurvey API")

# Security
security = HTTPBearer()

# Models
class TokenPayload(BaseModel):
    sub: str
    exp: int

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://synthsurvey.com",
        "https://synthsurvey.com",
        "http://www.synthsurvey.com",
        "https://www.synthsurvey.com",
        "http://localhost:3000",  # For local development
        "http://localhost:5000"   # For local development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # Updated to allow Authorization header
    expose_headers=["*"]
)

# Database connection parameters
DB_PARAMS = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

class WaitlistEntry(BaseModel):
    email: EmailStr

class TokenPurchase(BaseModel):
    amount: int
    payment_id: str

class Audience(BaseModel):
    name: str
    description: Optional[str]
    size: int
    demographics: dict

class Question(BaseModel):
    title: str
    description: Optional[str]
    question_type: str
    options: Optional[dict]

class Survey(BaseModel):
    title: str
    description: Optional[str]
    audience_id: int
    questions: List[int]
    token_cost: int

class SurveyQuestionUpdate(BaseModel):
    question_id: int
    order_number: int

# Auth0 Configuration
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "dev-16iksas57tijkr38.us.auth0.com")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "api.synthsurvey.com/")

def verify_token(token: str = Depends(security)) -> Dict:
    try:
        jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
        
        # Fetch JWKS
        response = requests.get(jwks_url)
        response.raise_for_status()
        jwks = response.json()

        # Decode header to get key ID
        unverified_header = jwt.get_unverified_header(token.credentials)
        rsa_key = next(
            (key for key in jwks["keys"] if key["kid"] == unverified_header["kid"]),
            None
        )

        if not rsa_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials"
            )

        # Construct the public key
        public_key = {
            "kty": rsa_key["kty"],
            "kid": rsa_key["kid"],
            "use": rsa_key["use"],
            "n": rsa_key["n"],
            "e": rsa_key["e"]
        }

        # Verify and decode the token
        payload = jwt.decode(
            token.credentials,
            key=jwt.algorithms.RSAAlgorithm.from_jwk(public_key),
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/"
        )

        return payload

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid claims. Please check the audience and issuer"
        )
    except PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Unable to parse authentication token: {str(e)}"
        )

# Utility Functions
def check_user_tokens(db_cursor, auth0_id: str, required_tokens: int) -> bool:
    """Check if user has sufficient tokens"""
    db_cursor.execute("""
        SELECT tokens_remaining 
        FROM users 
        WHERE auth0_id = %s
    """, (auth0_id,))
    
    result = db_cursor.fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
        
    return result['tokens_remaining'] >= required_tokens

def deduct_user_tokens(db_cursor, auth0_id: str, amount: int) -> int:
    """Deduct tokens from user's balance and return new balance"""
    db_cursor.execute("""
        UPDATE users 
        SET tokens_remaining = tokens_remaining - %s
        WHERE auth0_id = %s AND tokens_remaining >= %s
        RETURNING tokens_remaining
    """, (amount, auth0_id, amount))
    
    result = db_cursor.fetchone()
    if not result:
        raise HTTPException(status_code=400, detail="Insufficient tokens")
        
    return result['tokens_remaining']

def record_token_transaction(db_cursor, auth0_id: str, amount: int, 
                           transaction_type: str, description: Optional[str] = None):
    """Record a token transaction"""
    db_cursor.execute("""
        INSERT INTO tokens (user_id, amount, transaction_type, description)
        VALUES (
            (SELECT id FROM users WHERE auth0_id = %s),
            %s,
            %s,
            %s
        )
    """, (auth0_id, amount, transaction_type, description))

def get_survey_with_questions(db_cursor, survey_id: int, auth0_id: str):
    """Get survey details with its questions"""
    db_cursor.execute("""
        SELECT s.*, 
               array_agg(json_build_object(
                   'id', q.id,
                   'title', q.title,
                   'question_type', q.question_type,
                   'options', q.options,
                   'order_number', sq.order_number
               ) ORDER BY sq.order_number) as questions
        FROM surveys s
        LEFT JOIN survey_questions sq ON s.id = sq.survey_id
        LEFT JOIN questions q ON sq.question_id = q.id
        WHERE s.id = %s 
        AND s.user_id = (SELECT id FROM users WHERE auth0_id = %s)
        GROUP BY s.id
    """, (survey_id, auth0_id))
    
    result = db_cursor.fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Survey not found")
        
    return result

def get_survey_results_summary(db_cursor, survey_id: int, auth0_id: str):
    """Get summarized results for a survey"""
    db_cursor.execute("""
        SELECT 1 FROM surveys 
        WHERE id = %s 
        AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (survey_id, auth0_id))
    
    if not db_cursor.fetchone():
        raise HTTPException(status_code=404, detail="Survey not found")
    
    db_cursor.execute("""
        SELECT 
            COUNT(*) as total_responses,
            AVG(validation_score) as avg_validation_score,
            json_build_object(
                'responses', json_agg(response_data),
                'demographics', json_agg(respondent_demographics)
            ) as detailed_data
        FROM results
        WHERE survey_id = %s
        GROUP BY survey_id
    """, (survey_id,))
    
    return db_cursor.fetchone() or {
        'total_responses': 0,
        'avg_validation_score': 0,
        'detailed_data': {'responses': [], 'demographics': []}
    }

# Database connection
def get_db():
    conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

# Initialize database tables
def init_db():
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

# Waitlist Endpoint
@app.post("/waitlist")
async def add_to_waitlist(entry: WaitlistEntry):
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()
        
        # Insert new waitlist entry
        cur.execute(
            "INSERT INTO waitlist (email) VALUES (%s) RETURNING id",
            (entry.email,)
        )
        new_id = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {"status": "success", "message": "Added to waitlist", "id": new_id}
    
    except psycopg2.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )

# Token Management Endpoints
@app.post("/tokens/purchase")
async def purchase_tokens(
    purchase: TokenPurchase,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    try:
        cur = db.cursor()
        
        # Add tokens to user's balance
        cur.execute("""
            UPDATE users 
            SET tokens_remaining = tokens_remaining + %s 
            WHERE auth0_id = %s 
            RETURNING tokens_remaining
        """, (purchase.amount, user['sub']))
        
        # Record the transaction
        cur.execute("""
            INSERT INTO tokens (user_id, amount, transaction_type, description)
            VALUES ((SELECT id FROM users WHERE auth0_id = %s), %s, 'purchase', %s)
        """, (user['sub'], purchase.amount, f"Token purchase: {purchase.payment_id}"))
        
        db.commit()
        result = cur.fetchone()
        return {"success": True, "new_balance": result['tokens_remaining']}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audiences")
async def list_audiences(
    db = Depends(get_db),
    user = Depends(verify_token)
):
    cur = db.cursor()
    cur.execute("""
        SELECT * 
        FROM audiences
        WHERE user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (user['sub'],))
    return cur.fetchall()

# Audience Management Endpoints
@app.post("/audiences")
async def create_audience(
    audience: Audience,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    try:
        cur = db.cursor()
        
        # Convert demographics dict to JSON string
        demographics_json = json.dumps(audience.demographics)
        
        # Create the audience configuration
        cur.execute("""
            INSERT INTO audiences (user_id, name, description, size, demographics)
            VALUES ((SELECT id FROM users WHERE auth0_id = %s), %s, %s, %s, %s)
            RETURNING id
        """, (user['sub'], audience.name, audience.description, audience.size, demographics_json))
        
        db.commit()
        result = cur.fetchone()
        return {"id": result['id']}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/questions")
async def list_questions(
    db = Depends(get_db),
    user = Depends(verify_token)
):
    cur = db.cursor()
    cur.execute("""
        SELECT * FROM questions 
        WHERE user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (user['sub'],))
    return cur.fetchall()

# Survey Management Endpoints
@app.post("/surveys")
async def create_survey(
    survey: Survey,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    try:
        cur = db.cursor()
        
        # Check if user has enough tokens
        cur.execute("""
            SELECT tokens_remaining FROM users 
            WHERE auth0_id = %s AND tokens_remaining >= %s
        """, (user['sub'], survey.token_cost))
        
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Insufficient tokens")
        
        # Create survey
        cur.execute("""
            INSERT INTO surveys (user_id, title, description, audience_id, token_cost)
            VALUES ((SELECT id FROM users WHERE auth0_id = %s), %s, %s, %s, %s)
            RETURNING id
        """, (user['sub'], survey.title, survey.description, 
              survey.audience_id, survey.token_cost))
        
        survey_id = cur.fetchone()['id']
        
        # Add questions to survey
        for order, question_id in enumerate(survey.questions):
            cur.execute("""
                INSERT INTO survey_questions (survey_id, question_id, order_number)
                VALUES (%s, %s, %s)
            """, (survey_id, question_id, order))
        
        db.commit()
        return {"id": survey_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/surveys")
async def list_surveys(
    db = Depends(get_db),
    user = Depends(verify_token)
):
    cur = db.cursor()
    cur.execute("""
        SELECT s.*, array_agg(sq.question_id ORDER BY sq.order_number) as question_ids
        FROM surveys s
        LEFT JOIN survey_questions sq ON s.id = sq.survey_id
        WHERE s.user_id = (SELECT id FROM users WHERE auth0_id = %s)
        GROUP BY s.id
    """, (user['sub'],))
    return cur.fetchall()

# Survey Question Management Endpoints
@app.post("/surveys/{survey_id}/questions")
async def add_question_to_survey(
    survey_id: int,
    question: SurveyQuestionUpdate,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    try:
        cur = db.cursor()
        
        # Verify survey ownership and draft status
        cur.execute("""
            SELECT status FROM surveys 
            WHERE id = %s 
            AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
            AND status = 'draft'
        """, (survey_id, user['sub']))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Survey not found or not in draft status")
        
        # Add question to survey
        cur.execute("""
            INSERT INTO survey_questions (survey_id, question_id, order_number)
            VALUES (%s, %s, %s)
            ON CONFLICT (survey_id, question_id) 
            DO UPDATE SET order_number = EXCLUDED.order_number
        """, (survey_id, question.question_id, question.order_number))
        
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/surveys/{survey_id}/questions/{question_id}")
async def remove_question_from_survey(
    survey_id: int,
    question_id: int,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    try:
        cur = db.cursor()
        
        # Verify survey ownership and draft status
        cur.execute("""
            SELECT status FROM surveys 
            WHERE id = %s 
            AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
            AND status = 'draft'
        """, (survey_id, user['sub']))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Survey not found or not in draft status")
        
        # Remove question from survey
        cur.execute("""
            DELETE FROM survey_questions 
            WHERE survey_id = %s AND question_id = %s
        """, (survey_id, question_id))
        
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Results Management Endpoints
@app.get("/surveys/{survey_id}/results")
async def get_survey_results(
    survey_id: int,
    db = Depends(get_db),
    user = Depends(verify_token)
):
    cur = db.cursor()
    # Verify survey ownership
    cur.execute("""
        SELECT 1 FROM surveys 
        WHERE id = %s AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (survey_id, user['sub']))
    
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Survey not found")
    
    # Get results
    cur.execute("""
        SELECT * FROM results 
        WHERE survey_id = %s
        ORDER BY created_at DESC
    """, (survey_id,))
    
    return cur.fetchall()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

