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
