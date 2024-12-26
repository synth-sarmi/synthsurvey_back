import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, constr
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import jwt
import bcrypt
from uuid import uuid4
from dotenv import load_dotenv
import random
from functools import lru_cache

# Load environment variables
load_dotenv()

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', str(uuid4()))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

app = FastAPI(title="SynthSurvey API")

# Security
security = HTTPBearer()

# Auth Models
class UserSignup(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    
class UserLogin(BaseModel):
    email: EmailStr
    password: str

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
    allow_headers=["*"],
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

# Models
class WaitlistEntry(BaseModel):
    email: EmailStr

class TokenPurchase(BaseModel):
    amount: int
    payment_id: str

from typing import Dict, Any

class Audience(BaseModel):
    name: str
    description: Optional[str]
    size: int
    demographics: Dict[str, Any]

class Question(BaseModel):
    title: str
    description: Optional[str]
    question_type: str
    options: Optional[Dict[str, Any]]

class Survey(BaseModel):
    title: str
    description: Optional[str]
    audience_id: int
    questions: List[int]
    token_cost: int

class SurveyQuestionUpdate(BaseModel):
    question_id: int
    order_number: int

# Database connection
def get_db():
    conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

# JWT Token validation
async def validate_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        if datetime.fromtimestamp(payload['exp']) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

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

# Auth Endpoints
@app.post("/auth/signup")
async def signup(user: UserSignup, db = Depends(get_db)):
    try:
        cur = db.cursor()
        
        # Check if email already exists
        cur.execute("SELECT 1 FROM users WHERE email = %s", (user.email,))
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), salt)
        
        # Generate user_id
        user_id = str(uuid4())
        
        # Create user
        cur.execute("""
            INSERT INTO users (auth0_id, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id, email
        """, (user_id, user.email, hashed_password.decode('utf-8')))
        
        db.commit()
        new_user = cur.fetchone()
        
        # Generate JWT token
        token_expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        token_payload = {
            "sub": user_id,
            "email": user.email,
            "exp": token_expires.timestamp()
        }
        token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_EXPIRATION_HOURS * 3600
        }
        
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/auth/login")
async def login(user: UserLogin, db = Depends(get_db)):
    try:
        cur = db.cursor()
        
        # Get user
        cur.execute("""
            SELECT auth0_id, email, password_hash 
            FROM users 
            WHERE email = %s
        """, (user.email,))
        
        db_user = cur.fetchone()
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # Verify password
        if not bcrypt.checkpw(
            user.password.encode('utf-8'), 
            db_user['password_hash'].encode('utf-8')
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # Generate JWT token
        token_expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        token_payload = {
            "sub": db_user['auth0_id'],  # We're reusing auth0_id field as our user_id
            "email": db_user['email'],
            "exp": token_expires.timestamp()
        }
        token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_EXPIRATION_HOURS * 3600
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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
    user = Depends(validate_token)
):
    try:
        cur = db.cursor()
        print(f"Processing token purchase for user {user['sub']}")
        
        # Get user ID first
        cur.execute("""
            SELECT id, tokens_remaining 
            FROM users 
            WHERE auth0_id = %s
        """, (user['sub'],))
        
        user_data = cur.fetchone()
        print(f"Found user data: {user_data}")
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Add tokens to user's balance
        cur.execute("""
            UPDATE users 
            SET tokens_remaining = tokens_remaining + %s 
            WHERE id = %s 
            RETURNING id, tokens_remaining
        """, (purchase.amount, user_data['id']))
        
        update_result = cur.fetchone()
        print(f"Update result: {update_result}")
        
        if not update_result:
            raise HTTPException(status_code=500, detail="Failed to update token balance")
        
        # Record the transaction
        cur.execute("""
            INSERT INTO tokens (user_id, amount, transaction_type, description)
            VALUES (%s, %s, 'purchase', %s)
            RETURNING id
        """, (user_data['id'], purchase.amount, f"Token purchase: {purchase.payment_id}"))
        
        transaction_result = cur.fetchone()
        print(f"Transaction result: {transaction_result}")
        
        db.commit()
        return {
            "success": True, 
            "new_balance": update_result['tokens_remaining'],
            "transaction_id": transaction_result['id']
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Audience Management Endpoints
@app.post("/audiences")
async def create_audience(
    audience: Audience,
    db = Depends(get_db),
    user = Depends(validate_token)
):
    try:
        cur = db.cursor()
        
        # Create the audience configuration
        cur.execute("""
            INSERT INTO audiences (user_id, name, description, size, demographics)
            VALUES ((SELECT id FROM users WHERE auth0_id = %s), %s, %s, %s, %s)
            RETURNING id
        """, (user['sub'], audience.name, audience.description, audience.size, Json(audience.demographics)))
        
        audience_id = cur.fetchone()['id']
        
        # Sample people from ipumps table based on demographics
        conditions = []
        params = []
        if 'age' in audience.demographics:
            age_range = audience.demographics['age'].split('-')
            if len(age_range) == 2:
                conditions.append('"AGE" >= %s AND "AGE" <= %s')
                params.extend([int(age_range[0]), int(age_range[1])])

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Build the sampling query
        sampling_query = f"""
            WITH sampled_people AS (
                SELECT "SERIAL" as id, 
                       jsonb_build_object(
                           'age', "AGE"::text,
                           'gender', "SEX",
                           'education', "EDUC",
                           'income', "INCTOT"::text
                       ) as demographics
                FROM ipumps
                WHERE {where_clause}
                ORDER BY RANDOM()
                LIMIT %s
            )
            INSERT INTO audience_members (audience_id, user_id, ipump_id, demographics)
            SELECT %s, (SELECT id FROM users WHERE auth0_id = %s), id, demographics
            FROM sampled_people
        """
        
        # Add size and other parameters
        params.extend([audience.size, audience_id, user['sub']])
        cur.execute(sampling_query, params)
        
        db.commit()
        return {"id": audience_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audiences")
async def list_audiences(
    db = Depends(get_db),
    user = Depends(validate_token)
):
    cur = db.cursor()
    cur.execute("""
        SELECT a.*, COUNT(am.id) as current_size 
        FROM audiences a
        LEFT JOIN audience_members am ON a.id = am.audience_id
        WHERE a.user_id = (SELECT id FROM users WHERE auth0_id = %s)
        GROUP BY a.id
    """, (user['sub'],))
    return cur.fetchall()

@app.get("/audiences/{audience_id}/members")
async def get_audience_members(
    audience_id: int,
    db = Depends(get_db),
    user = Depends(validate_token)
):
    cur = db.cursor()
    cur.execute("""
        SELECT am.* 
        FROM audience_members am
        WHERE am.audience_id = %s 
        AND am.user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (audience_id, user['sub']))
    return cur.fetchall()

# Question Management Endpoints
@app.post("/questions")
async def create_question(
    question: Question,
    db = Depends(get_db),
    user = Depends(validate_token)
):
    try:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO questions (user_id, title, description, question_type, options)
            VALUES ((SELECT id FROM users WHERE auth0_id = %s), %s, %s, %s, %s)
            RETURNING id
        """, (user['sub'], question.title, question.description, 
              question.question_type, Json(question.options) if question.options else None))
        db.commit()
        result = cur.fetchone()
        return {"id": result['id']}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/questions")
async def list_questions(
    db = Depends(get_db),
    user = Depends(validate_token)
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
    user = Depends(validate_token)
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
    user = Depends(validate_token)
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
    user = Depends(validate_token)
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
    user = Depends(validate_token)
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
    user = Depends(validate_token)
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
