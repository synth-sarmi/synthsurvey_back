# API Testing Guide

This guide provides curl commands to test all endpoints locally. First, make sure the server is running:
```bash
python main.py
```

## Authentication

1. **Create a new user (signup)**:
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }'
```

2. **Login to get a token**:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }'
```

Save the access_token from the response. For the following commands, replace YOUR_TOKEN with this value.

## Token Management

**Purchase tokens**:
```bash
curl -X POST http://localhost:8000/tokens/purchase \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "amount": 100,
    "payment_id": "test_payment_123"
  }'
```

## Audience Management

1. **Create an audience**:
```bash
curl -X POST http://localhost:8000/audiences \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test Audience",
    "description": "Test audience description",
    "size": 100,
    "demographics": {
      "age": "18-35"
    }
  }'
```

2. **List audiences**:
```bash
curl -X GET http://localhost:8000/audiences \
  -H "Authorization: Bearer YOUR_TOKEN"
```

3. **Get audience members**:
```bash
# Replace AUDIENCE_ID with the id from create audience response
curl -X GET http://localhost:8000/audiences/AUDIENCE_ID/members \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Question Management

1. **Create a question**:
```bash
curl -X POST http://localhost:8000/questions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "What is your favorite color?",
    "description": "Choose your preferred color",
    "question_type": "multiple_choice",
    "options": {
      "choices": ["Red", "Blue", "Green", "Yellow"]
    }
  }'
```

2. **List questions**:
```bash
curl -X GET http://localhost:8000/questions \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Survey Management

1. **Create a survey**:
```bash
# Replace AUDIENCE_ID and QUESTION_ID with values from previous responses
curl -X POST http://localhost:8000/surveys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "Color Preference Survey",
    "description": "A survey about color preferences",
    "audience_id": AUDIENCE_ID,
    "questions": [QUESTION_ID],
    "token_cost": 50
  }'
```

2. **List surveys**:
```bash
curl -X GET http://localhost:8000/surveys \
  -H "Authorization: Bearer YOUR_TOKEN"
```

3. **Add question to survey**:
```bash
# Replace SURVEY_ID and QUESTION_ID
curl -X POST http://localhost:8000/surveys/SURVEY_ID/questions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "question_id": QUESTION_ID,
    "order_number": 1
  }'
```

4. **Remove question from survey**:
```bash
# Replace SURVEY_ID and QUESTION_ID
curl -X DELETE http://localhost:8000/surveys/SURVEY_ID/questions/QUESTION_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

5. **Get survey results**:
```bash
# Replace SURVEY_ID
curl -X GET http://localhost:8000/surveys/SURVEY_ID/results \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Testing Flow Example

Here's a complete flow to test all functionality:

1. Create a user and get token:
```bash
# Signup
TOKEN=$(curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }' | jq -r .access_token)

# Or login if user exists
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }' | jq -r .access_token)
```

2. Purchase tokens:
```bash
curl -X POST http://localhost:8000/tokens/purchase \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "amount": 100,
    "payment_id": "test_payment_123"
  }'
```

3. Create an audience:
```bash
AUDIENCE_ID=$(curl -X POST http://localhost:8000/audiences \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Test Audience",
    "description": "Test audience description",
    "size": 100,
    "demographics": {
      "age": "18-35"
    }
  }' | jq -r .id)
```

4. Create a question:
```bash
QUESTION_ID=$(curl -X POST http://localhost:8000/questions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "title": "What is your favorite color?",
    "description": "Choose your preferred color",
    "question_type": "multiple_choice",
    "options": {
      "choices": ["Red", "Blue", "Green", "Yellow"]
    }
  }' | jq -r .id)
```

5. Create a survey:
```bash
SURVEY_ID=$(curl -X POST http://localhost:8000/surveys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"title\": \"Color Preference Survey\",
    \"description\": \"A survey about color preferences\",
    \"audience_id\": $AUDIENCE_ID,
    \"questions\": [$QUESTION_ID],
    \"token_cost\": 50
  }" | jq -r .id)
```

6. View results:
```bash
curl -X GET http://localhost:8000/surveys/$SURVEY_ID/results \
  -H "Authorization: Bearer $TOKEN"
```

Note: The above flow assumes you have `jq` installed for JSON processing. If not, you'll need to manually copy the IDs from each response.
