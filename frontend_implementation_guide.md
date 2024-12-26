# Frontend Implementation Guide

## Setup

First, set up your API client with authentication handling:

```typescript
// src/api/client.ts
import axios from 'axios';

const API_URL = 'http://localhost:8000';  // Update for production

// Create axios instance
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

## Authentication

### Types
```typescript
// src/types/auth.ts
export interface SignupData {
  email: string;
  password: string;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}
```

### API Service
```typescript
// src/services/auth.ts
import apiClient from '../api/client';
import { SignupData, LoginData, AuthResponse } from '../types/auth';

export const authService = {
  async signup(data: SignupData): Promise<void> {
    const response = await apiClient.post<AuthResponse>('/auth/signup', data);
    localStorage.setItem('auth_token', response.data.access_token);
  },

  async login(data: LoginData): Promise<void> {
    const response = await apiClient.post<AuthResponse>('/auth/login', data);
    localStorage.setItem('auth_token', response.data.access_token);
  },

  logout(): void {
    localStorage.removeItem('auth_token');
  },
};
```

### React Components
```typescript
// src/components/auth/LoginForm.tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '../../services/auth';

export const LoginForm: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await authService.login({ email, password });
      navigate('/dashboard');
    } catch (err) {
      setError('Invalid credentials');
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        required
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        required
      />
      {error && <div className="error">{error}</div>}
      <button type="submit">Login</button>
    </form>
  );
};
```

## Token Management

### Types
```typescript
// src/types/tokens.ts
export interface TokenPurchase {
  amount: number;
  payment_id: string;
}

export interface TokenResponse {
  success: boolean;
  new_balance: number;
  transaction_id: number;
}
```

### API Service
```typescript
// src/services/tokens.ts
import apiClient from '../api/client';
import { TokenPurchase, TokenResponse } from '../types/tokens';

export const tokenService = {
  async purchaseTokens(data: TokenPurchase): Promise<TokenResponse> {
    const response = await apiClient.post<TokenResponse>('/tokens/purchase', data);
    return response.data;
  },
};
```

## Audience Management

### Types
```typescript
// src/types/audiences.ts
export interface Demographics {
  age?: string;
  gender?: string;
  education?: string;
  income?: string;
}

export interface Audience {
  name: string;
  description?: string;
  size: number;
  demographics: Demographics;
}

export interface AudienceResponse {
  id: number;
}

export interface AudienceMember {
  id: number;
  demographics: Demographics;
}
```

### API Service
```typescript
// src/services/audiences.ts
import apiClient from '../api/client';
import { Audience, AudienceResponse, AudienceMember } from '../types/audiences';

export const audienceService = {
  async createAudience(data: Audience): Promise<AudienceResponse> {
    const response = await apiClient.post<AudienceResponse>('/audiences', data);
    return response.data;
  },

  async listAudiences(): Promise<Audience[]> {
    const response = await apiClient.get<Audience[]>('/audiences');
    return response.data;
  },

  async getAudienceMembers(audienceId: number): Promise<AudienceMember[]> {
    const response = await apiClient.get<AudienceMember[]>(`/audiences/${audienceId}/members`);
    return response.data;
  },
};
```

### React Components
```typescript
// src/components/audiences/CreateAudienceForm.tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { audienceService } from '../../services/audiences';
import { Audience } from '../../types/audiences';

export const CreateAudienceForm: React.FC = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [size, setSize] = useState(100);
  const [ageRange, setAgeRange] = useState('18-35');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const audienceData: Audience = {
        name,
        description,
        size,
        demographics: {
          age: ageRange,
        },
      };
      await audienceService.createAudience(audienceData);
      navigate('/audiences');
    } catch (err) {
      setError('Failed to create audience');
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Audience Name"
        required
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
      />
      <input
        type="number"
        value={size}
        onChange={(e) => setSize(parseInt(e.target.value))}
        min="1"
        required
      />
      <select value={ageRange} onChange={(e) => setAgeRange(e.target.value)}>
        <option value="18-35">18-35</option>
        <option value="36-50">36-50</option>
        <option value="51-65">51-65</option>
      </select>
      {error && <div className="error">{error}</div>}
      <button type="submit">Create Audience</button>
    </form>
  );
};
```

## Question Management

### Types
```typescript
// src/types/questions.ts
export interface QuestionOptions {
  choices?: string[];
}

export interface Question {
  title: string;
  description?: string;
  question_type: string;
  options?: QuestionOptions;
}

export interface QuestionResponse {
  id: number;
}
```

### API Service
```typescript
// src/services/questions.ts
import apiClient from '../api/client';
import { Question, QuestionResponse } from '../types/questions';

export const questionService = {
  async createQuestion(data: Question): Promise<QuestionResponse> {
    const response = await apiClient.post<QuestionResponse>('/questions', data);
    return response.data;
  },

  async listQuestions(): Promise<Question[]> {
    const response = await apiClient.get<Question[]>('/questions');
    return response.data;
  },
};
```

## Survey Management

### Types
```typescript
// src/types/surveys.ts
export interface Survey {
  title: string;
  description?: string;
  audience_id: number;
  questions: number[];
  token_cost: number;
}

export interface SurveyResponse {
  id: number;
}

export interface SurveyQuestion {
  question_id: number;
  order_number: number;
}
```

### API Service
```typescript
// src/services/surveys.ts
import apiClient from '../api/client';
import { Survey, SurveyResponse, SurveyQuestion } from '../types/surveys';

export const surveyService = {
  async createSurvey(data: Survey): Promise<SurveyResponse> {
    const response = await apiClient.post<SurveyResponse>('/surveys', data);
    return response.data;
  },

  async listSurveys(): Promise<Survey[]> {
    const response = await apiClient.get<Survey[]>('/surveys');
    return response.data;
  },

  async addQuestionToSurvey(surveyId: number, data: SurveyQuestion): Promise<void> {
    await apiClient.post(`/surveys/${surveyId}/questions`, data);
  },

  async removeQuestionFromSurvey(surveyId: number, questionId: number): Promise<void> {
    await apiClient.delete(`/surveys/${surveyId}/questions/${questionId}`);
  },

  async getSurveyResults(surveyId: number): Promise<any[]> {
    const response = await apiClient.get(`/surveys/${surveyId}/results`);
    return response.data;
  },
};
```

## Usage Example

Here's a complete example of creating a survey with an audience and questions:

```typescript
// src/pages/CreateSurveyPage.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { audienceService } from '../services/audiences';
import { questionService } from '../services/questions';
import { surveyService } from '../services/surveys';
import { Audience } from '../types/audiences';
import { Question } from '../types/questions';

export const CreateSurveyPage: React.FC = () => {
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [audienceId, setAudienceId] = useState<number>();
  const [selectedQuestions, setSelectedQuestions] = useState<number[]>([]);
  const [tokenCost, setTokenCost] = useState(50);
  const [audiences, setAudiences] = useState<Audience[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadData = async () => {
      try {
        const [audiencesData, questionsData] = await Promise.all([
          audienceService.listAudiences(),
          questionService.listQuestions(),
        ]);
        setAudiences(audiencesData);
        setQuestions(questionsData);
      } catch (err) {
        setError('Failed to load data');
      }
    };
    loadData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!audienceId) {
      setError('Please select an audience');
      return;
    }
    try {
      await surveyService.createSurvey({
        title,
        description,
        audience_id: audienceId,
        questions: selectedQuestions,
        token_cost: tokenCost,
      });
      navigate('/surveys');
    } catch (err) {
      setError('Failed to create survey');
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Survey Title"
        required
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
      />
      <select
        value={audienceId}
        onChange={(e) => setAudienceId(parseInt(e.target.value))}
        required
      >
        <option value="">Select Audience</option>
        {audiences.map((audience) => (
          <option key={audience.id} value={audience.id}>
            {audience.name}
          </option>
        ))}
      </select>
      <div>
        <h3>Select Questions</h3>
        {questions.map((question) => (
          <label key={question.id}>
            <input
              type="checkbox"
              checked={selectedQuestions.includes(question.id)}
              onChange={(e) => {
                if (e.target.checked) {
                  setSelectedQuestions([...selectedQuestions, question.id]);
                } else {
                  setSelectedQuestions(
                    selectedQuestions.filter((id) => id !== question.id)
                  );
                }
              }}
            />
            {question.title}
          </label>
        ))}
      </div>
      <input
        type="number"
        value={tokenCost}
        onChange={(e) => setTokenCost(parseInt(e.target.value))}
        min="1"
        required
      />
      {error && <div className="error">{error}</div>}
      <button type="submit">Create Survey</button>
    </form>
  );
};
```

## Error Handling

Add this type for consistent error handling:

```typescript
// src/types/error.ts
export interface ApiError {
  detail: string;
}

// Usage in services
try {
  // API call
} catch (error) {
  if (axios.isAxiosError(error) && error.response?.data) {
    const apiError = error.response.data as ApiError;
    throw new Error(apiError.detail);
  }
  throw error;
}
```

## Protected Route Component

```typescript
// src/components/ProtectedRoute.tsx
import { Navigate, useLocation } from 'react-router-dom';

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const token = localStorage.getItem('auth_token');
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

// Usage in App.tsx
const App = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route
      path="/dashboard"
      element={
        <ProtectedRoute>
          <DashboardPage />
        </ProtectedRoute>
      }
    />
  </Routes>
);
```

This implementation guide provides a complete TypeScript/React setup for interacting with the API, including:
- Type definitions for all requests/responses
- Service layers for API communication
- React components with proper error handling
- Protected routes
- Form handling
- Token management
- Axios interceptors for authentication

Remember to:
1. Update API_URL for your environment
2. Add proper error handling
3. Add loading states
4. Add proper form validation
5. Add proper TypeScript types for all components
6. Add proper styling
