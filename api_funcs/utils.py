import os
import jwt
import json
import httpx
from typing import Dict, Optional
from fastapi import HTTPException
from datetime import datetime
from functools import lru_cache

@lru_cache()
async def get_auth0_public_key():
    """Fetch and cache Auth0 public key for token validation"""
    try:
        auth0_domain = os.getenv('AUTH0_DOMAIN')
        url = f'https://{auth0_domain}/.well-known/jwks.json'
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Auth0 public key: {str(e)}")

async def validate_auth0_token(token: str) -> Dict:
    """
    Validate Auth0 JWT token and return payload
    In production, implement full JWT validation using Auth0's JWKS
    """
    try:
        # Decode token without verification for development
        # In production, implement proper verification using Auth0's public key
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        
        if 'sub' not in payload:
            raise HTTPException(status_code=401, detail="Invalid token payload")
            
        return payload
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

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
    # Verify survey ownership and get details
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
    # Verify survey ownership
    db_cursor.execute("""
        SELECT 1 FROM surveys 
        WHERE id = %s 
        AND user_id = (SELECT id FROM users WHERE auth0_id = %s)
    """, (survey_id, auth0_id))
    
    if not db_cursor.fetchone():
        raise HTTPException(status_code=404, detail="Survey not found")
    
    # Get results with basic analytics
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
