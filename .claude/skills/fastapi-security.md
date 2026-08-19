# FastAPI-Specific Security Review Skill

Review FastAPI applications for FastAPI-specific security vulnerabilities and best practices.

## What to Check

### 1. Dependency Injection & Authentication

**Missing Authentication**
```python
# ❌ VULNERABLE - No authentication required
@app.get("/api/users")
async def get_users():
    return await db.get_users()  # Anyone can access!

# ✅ SECURE - Authentication required
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    if not user:
        raise HTTPException(status_code=401)
    return user

@app.get("/api/users")
async def get_users(current_user: User = Depends(get_current_user)):
    return await db.get_users()
```

**Weak Authentication**
```python
# ❌ BAD - Basic auth without HTTPS
from fastapi.security import HTTPBasic

security = HTTPBasic()  # Transmits credentials in base64

# ✅ SECURE - Use OAuth2 or JWT
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
```

### 2. Authorization & RBAC

**Missing Authorization Check**
```python
# ❌ VULNERABLE - Authenticated but no authorization check
@app.delete("/api/resources/{id}")
async def delete_resource(id: str, user: User = Depends(get_current_user)):
    # Any authenticated user can delete!
    await db.delete_resource(id)
    return {"success": True}

# ✅ SECURE - Role-based authorization
@app.delete("/api/resources/{id}")
async def delete_resource(
    id: str,
    user: User = Depends(get_current_user)
):
    if not user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin required")
    await db.delete_resource(id)
    return {"success": True}
```

**No Resource Ownership Check**
```python
# ❌ VULNERABLE - User can access any resource
@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str, user: User = Depends(get_current_user)):
    return await db.get_document(doc_id)  # Any user can access any doc!

# ✅ SECURE - Check resource ownership
@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str, user: User = Depends(get_current_user)):
    doc = await db.get_document(doc_id)
    if doc.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your document")
    return doc
```

### 3. Input Validation

**Missing Request Validation**
```python
# ❌ VULNERABLE - No validation
@app.post("/api/users")
async def create_user(user: dict):
    return await db.create_user(**user)  # Any data accepted!

# ✅ SECURE - Pydantic validation
from pydantic import BaseModel, EmailStr, Field, validator

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)

    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v

@app.post("/api/users")
async def create_user(user: UserCreate):
    return await db.create_user(user.dict())
```

**SQL Injection**
```python
# ❌ VULNERABLE - String concatenation
@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return await db.execute(query)  # SQL injection!

# ✅ SECURE - Parameterized query
@app.get("/api/users/{user_id}")
async def get_user(user_id: int):  # Type validation
    query = "SELECT * FROM users WHERE id = $1"
    return await db.execute(query, user_id)
```

### 4. CORS Configuration

**Overly Permissive CORS**
```python
# ❌ VULNERABLE - Allows any origin
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Any origin can access!
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ SECURE - Specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.example.com",
        "https://admin.example.com"
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)
```

### 5. Rate Limiting

**No Rate Limiting**
```python
# ❌ BAD - No rate limit, can be abused
@app.post("/api/expensive-operation")
async def expensive_operation():
    # Resource-intensive operation
    pass

# ✅ SECURE - Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/expensive-operation")
@limiter.limit("10/minute")
async def expensive_operation():
    # Resource-intensive operation
    pass
```

### 6. Security Headers

**Missing Security Headers**
```python
# ✅ SECURE - Add security middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

### 7. Error Handling

**Information Disclosure in Errors**
```python
# ❌ BAD - Exposes sensitive information
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exc()}
    )  # Exposes internals!

# ✅ SECURE - Generic error message
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

### 8. File Uploads

**Unrestricted File Uploads**
```python
# ❌ VULNERABLE - Accepts any file
@app.post("/upload")
async def upload_file(file: UploadFile):
    content = await file.read()
    with open(f"/uploads/{file.filename}", "wb") as f:
        f.write(content)  # Malicious files uploaded!

# ✅ SECURE - Validate uploads
import os
import magic

@app.post("/upload")
async def upload_file(file: UploadFile):
    # Check file size
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "File too large")

    # Check file type
    mime = magic.from_buffer(content, mime=True)
    allowed_types = ["image/jpeg", "image/png", "application/pdf"]
    if mime not in allowed_types:
        raise HTTPException(400, "Invalid file type")

    # Sanitize filename
    safe_filename = os.path.basename(file.filename)
    if not safe_filename.isalnum():
        raise HTTPException(400, "Invalid filename")

    # Save with restricted permissions
    filepath = f"/uploads/{safe_filename}"
    with open(filepath, "wb") as f:
        os.chmod(filepath, 0o600)  # Owner only
        f.write(content)
```

### 9. Async/Await Security

**Blocking Operations in Async**
```python
# ❌ BAD - Blocks event loop
@app.get("/api/data")
async def get_data():
    time.sleep(10)  # Blocks entire app!
    return {"data": "result"}

# ✅ SECURE - Non-blocking
import asyncio

@app.get("/api/data")
async def get_data():
    await asyncio.sleep(10)  # Non-blocking
    return {"data": "result"}
```

### 10. Database Security

**SQL Injection**
```python
# ❌ VULNERABLE - Raw SQL with user input
@app.get("/api/search")
async def search(query: str):
    return await db.execute(f"SELECT * FROM items WHERE name LIKE '%{query}%'")

# ✅ SECURE - Parameterized or ORM
@app.get("/api/search")
async def search(query: str):
    # Using SQLAlchemy with parameters
    return await db.execute(
        "SELECT * FROM items WHERE name LIKE :query",
        {"query": f"%{query}%"}
    )
```

**Connection Pool Security**
```python
# ❌ BAD - No SSL verification
engine = create_async_engine("postgresql://user:pass@host/db")

# ✅ SECURE - SSL enforced
engine = create_async_engine(
    "postgresql://user:pass@host/db",
    connect_args={"sslmode": "require"}
)
```

### 11. API Security

**No API Versioning**
```python
# ❌ BAD - No version, breaking changes affect clients
@app.get("/api/users")
async def get_users():
    return await db.get_users()

# ✅ GOOD - Versioned API
@app.get("/api/v1/users")
async def get_users_v1():
    return await db.get_users_v1()
```

**Pagination Issues**
```python
# ❌ BAD - No limit, can fetch millions of records
@app.get("/api/users")
async def get_users():
    return await db.get_all_users()  # All users!

# ✅ SECURE - Paginated with limit
@app.get("/api/users")
async def get_users(skip: int = 0, limit: int = 100):
    if limit > 1000:
        raise HTTPException(400, "Limit too large")
    return await db.get_users(skip=skip, limit=limit)
```

### 12. Background Tasks Security

**Unsafe Background Tasks**
```python
# ❌ BAD - User input directly in background task
@app.post("/api/process")
async def process_data(data: dict):
    # No validation before background task
    BackgroundTasks.add_task(process_unvalidated, data)
    return {"status": "processing"}

# ✅ SECURE - Validate first
@app.post("/api/process")
async def process_data(data: DataModel):
    # Validate before background task
    BackgroundTasks.add_task(process_validated, data)
    return {"status": "processing"}
```

### 13. WebSocket Security

**Missing WebSocket Authentication**
```python
# ❌ VULNERABLE - No auth on WebSocket
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Anyone can connect!

# ✅ SECURE - Authenticated WebSocket
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)):
    user = await verify_token(token)
    if not user:
        await websocket.close(code=1008)
        return
    await websocket.accept()
```

## Review Checklist

For each FastAPI file, check:

- [ ] Authentication required for protected endpoints
- [ ] Authorization checks for role-based access
- [ ] Resource ownership verification
- [ ] Input validation with Pydantic models
- [ ] SQL injection prevention with parameterized queries
- [ ] CORS configured with specific origins
- [ ] Rate limiting on expensive operations
- [ ] Security headers middleware configured
- [ ] Error messages don't expose sensitive information
- [ ] File uploads validated and sanitized
- [ ] Async operations don't block event loop
- [ ] Database connections use SSL/TLS
- [ ] API versioning implemented
- [ ] Pagination with reasonable limits
- [ ] Background tasks validate input first
- [ ] WebSocket connections authenticated

## Output Format

```markdown
## FastAPI Security Review: [file_name]

### Critical
- [Issue] - [Security impact] - [Recommendation]

### High
- [Issue] - [Security impact] - [Recommendation]

### Medium
- [Issue] - [Security impact] - [Recommendation]

### Low
- [Issue] - [Security impact] - [Recommendation]

### Positive Patterns
+ [Good security practice found]
```
