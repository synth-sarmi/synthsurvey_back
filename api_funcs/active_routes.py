from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, constr, HttpUrl
import jwt
import bcrypt
from datetime import datetime, timedelta
from uuid import uuid4
import psycopg2
from psycopg2.extras import Json
from typing import Dict, Any, Optional
import os

# JWT Configuration from environment
JWT_SECRET = os.getenv('JWT_SECRET', str(uuid4()))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

router = APIRouter()
security = HTTPBearer()

# Models
class UserSignup(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class WaitlistEntry(BaseModel):
    email: EmailStr

class Audience(BaseModel):
    name: str
    description: Optional[str]
    size: int
    demographics: Dict[str, Any]

class SurveyCreate(BaseModel):
    audience_id: int
    url: HttpUrl
    url_type: str

class SurveyResponse(BaseModel):
    id: int
    audience_id: int
    url: str
    url_type: str
    status: str
    responses_generated: int
    total_responses: int
    created_at: datetime
    updated_at: datetime

# Database connection parameters from environment
DB_PARAMS = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

# Database connection
def get_db():
    conn = psycopg2.connect(**DB_PARAMS, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

# JWT Token validation
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
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

# Auth Endpoints
@router.post("/auth/signup")
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

@router.post("/auth/login")
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
            "sub": db_user['auth0_id'],
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
@router.post("/waitlist")
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

# Audience Management Endpoints
@router.post("/audiences")
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
        db.commit()
        return {"id": audience_id}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/audiences")
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

@router.post("/surveys", response_model=SurveyResponse)
async def create_survey(
    survey: SurveyCreate,
    db = Depends(get_db),
    user = Depends(validate_token)
):
    try:
        cur = db.cursor()
        
        # Verify the audience belongs to the user
        cur.execute("""
            SELECT size FROM audiences 
            WHERE id = %s AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
        """, (survey.audience_id, user['sub']))
        
        audience = cur.fetchone()
        if not audience:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audience not found or doesn't belong to user"
            )
        
        # Create the survey
        cur.execute("""
            INSERT INTO surveys 
            (user_id, audience_id, url, url_type, total_responses)
            VALUES (
                (SELECT id FROM users WHERE auth0_id = %s),
                %s, %s, %s, %s
            )
            RETURNING *
        """, (
            user['sub'],
            survey.audience_id,
            str(survey.url),
            survey.url_type,
            audience['size']
        ))
        
        new_survey = cur.fetchone()
        db.commit()
        return new_survey
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/surveys", response_model=list[SurveyResponse])
async def list_surveys(
    db = Depends(get_db),
    user = Depends(validate_token)
):
    try:
        cur = db.cursor()
        cur.execute("""
            SELECT s.*, a.size as audience_size
            FROM surveys s
            JOIN audiences a ON s.audience_id = a.id
            WHERE s.user_id = (SELECT id FROM users WHERE auth0_id = %s)
            ORDER BY s.created_at DESC
        """, (user['sub'],))
        return cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
