from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import psycopg2
from psycopg2.extras import Json
import os
from .active_routes import validate_token, get_db

router = APIRouter()

# Models
class TokenPurchase(BaseModel):
    amount: int
    payment_id: str

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

# Token Management Endpoints
@router.post("/tokens/purchase")
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

# Question Management Endpoints
@router.post("/questions")
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

@router.get("/questions")
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
@router.post("/surveys")
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

@router.get("/surveys")
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
@router.post("/surveys/{survey_id}/questions")
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

@router.delete("/surveys/{survey_id}/questions/{question_id}")
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
@router.get("/surveys/{survey_id}/results")
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
