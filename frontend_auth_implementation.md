# Frontend Authentication Implementation Guide

## Overview
This guide explains how to implement the new custom authentication system in the frontend, replacing the previous Auth0 implementation.

## Authentication Flow

1. **User Registration (Signup)**
   - Endpoint: `POST /auth/signup`
   - Request Body:
   ```javascript
   {
     "email": "user@example.com",
     "password": "securepassword123" // minimum 8 characters
   }
   ```
   - Response:
   ```javascript
   {
     "access_token": "eyJhbGc...", // JWT token
     "token_type": "bearer",
     "expires_in": 86400 // 24 hours in seconds
   }
   ```

2. **User Login**
   - Endpoint: `POST /auth/login`
   - Request Body:
   ```javascript
   {
     "email": "user@example.com",
     "password": "securepassword123"
   }
   ```
   - Response: Same as signup

## Implementation Steps

1. **Token Management**
   ```typescript
   // utils/auth.ts
   
   const TOKEN_KEY = 'auth_token';
   const TOKEN_EXPIRY_KEY = 'auth_token_expiry';
   
   export const saveToken = (token: string, expiresIn: number) => {
     localStorage.setItem(TOKEN_KEY, token);
     const expiryTime = Date.now() + (expiresIn * 1000);
     localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
   };
   
   export const getToken = (): string | null => {
     const token = localStorage.getItem(TOKEN_KEY);
     const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
     
     if (!token || !expiry) return null;
     
     if (Date.now() > parseInt(expiry)) {
       // Token expired
       localStorage.removeItem(TOKEN_KEY);
       localStorage.removeItem(TOKEN_EXPIRY_KEY);
       return null;
     }
     
     return token;
   };
   
   export const removeToken = () => {
     localStorage.removeItem(TOKEN_KEY);
     localStorage.removeItem(TOKEN_EXPIRY_KEY);
   };
   ```

2. **API Client Setup**
   ```typescript
   // api/client.ts
   
   import axios from 'axios';
   import { getToken } from '../utils/auth';
   
   const API_URL = 'http://your-api-url';
   
   const apiClient = axios.create({
     baseURL: API_URL,
     headers: {
       'Content-Type': 'application/json',
     },
   });
   
   // Add auth token to requests
   apiClient.interceptors.request.use((config) => {
     const token = getToken();
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
         removeToken();
         // Redirect to login page
         window.location.href = '/login';
       }
       return Promise.reject(error);
   });
   ```

3. **Authentication Service**
   ```typescript
   // services/auth.ts
   
   import { apiClient } from '../api/client';
   import { saveToken, removeToken } from '../utils/auth';
   
   interface AuthResponse {
     access_token: string;
     token_type: string;
     expires_in: number;
   }
   
   export const authService = {
     async signup(email: string, password: string): Promise<void> {
       const response = await apiClient.post<AuthResponse>('/auth/signup', {
         email,
         password,
       });
       saveToken(response.data.access_token, response.data.expires_in);
     },
   
     async login(email: string, password: string): Promise<void> {
       const response = await apiClient.post<AuthResponse>('/auth/login', {
         email,
         password,
       });
       saveToken(response.data.access_token, response.data.expires_in);
     },
   
     logout(): void {
       removeToken();
     },
   };
   ```

4. **Protected Route Component**
   ```typescript
   // components/ProtectedRoute.tsx
   
   import { Navigate } from 'react-router-dom';
   import { getToken } from '../utils/auth';
   
   interface ProtectedRouteProps {
     children: React.ReactNode;
   }
   
   export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
     const token = getToken();
     
     if (!token) {
       return <Navigate to="/login" replace />;
     }
     
     return <>{children}</>;
   };
   ```

5. **Usage in Routes**
   ```typescript
   // App.tsx
   
   import { BrowserRouter, Routes, Route } from 'react-router-dom';
   import { ProtectedRoute } from './components/ProtectedRoute';
   
   export const App = () => {
     return (
       <BrowserRouter>
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
       </BrowserRouter>
     );
   };
   ```

6. **Login Form Example**
   ```typescript
   // pages/LoginPage.tsx
   
   import { useState } from 'react';
   import { useNavigate } from 'react-router-dom';
   import { authService } from '../services/auth';
   
   export const LoginPage = () => {
     const navigate = useNavigate();
     const [email, setEmail] = useState('');
     const [password, setPassword] = useState('');
     const [error, setError] = useState('');
   
     const handleSubmit = async (e: React.FormEvent) => {
       e.preventDefault();
       try {
         await authService.login(email, password);
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

## Error Handling

The API returns the following error responses:

1. **Invalid Credentials** (401)
   ```javascript
   {
     "detail": "Invalid credentials"
   }
   ```

2. **Email Already Registered** (400)
   ```javascript
   {
     "detail": "Email already registered"
   }
   ```

3. **Invalid Token** (401)
   ```javascript
   {
     "detail": "Invalid authentication credentials"
   }
   ```

## Security Considerations

1. Always use HTTPS in production
2. Store tokens in localStorage (or sessionStorage for more security)
3. Implement proper password validation (minimum length, complexity)
4. Add rate limiting for login attempts
5. Implement proper error handling and user feedback
6. Clear tokens on logout and 401 responses
7. Validate token expiration before making requests

## Migration from Auth0

1. Remove Auth0 SDK and configuration
2. Replace Auth0 login/signup UI with custom forms
3. Update protected routes to use new token validation
4. Update API calls to use new token format
5. Test all authenticated flows thoroughly

## Testing Checklist

- [ ] User can sign up with valid email/password
- [ ] User can't sign up with existing email
- [ ] User can log in with valid credentials
- [ ] User can't log in with invalid credentials
- [ ] Protected routes redirect to login when no token
- [ ] Protected routes accessible with valid token
- [ ] Token expiration handled correctly
- [ ] Logout clears token and redirects
- [ ] API calls include authorization header
- [ ] 401 responses handled correctly
