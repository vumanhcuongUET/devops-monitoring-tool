# REST API Security Review Skill

Review REST API endpoints and implementations for API-specific security vulnerabilities and best practices.

## What to Check

### 1. Authentication & Authorization

**Missing Authentication**
```python
# ❌ VULNERABLE - No authentication required
@app.get("/api/users")
def get_users():
    return jsonify(users)  # Anyone can access!

# ✅ SECURE - Authentication required
@app.get("/api/users")
@auth_required  # Custom decorator
def get_users():
    current_user = get_current_user()
    return jsonify(get_users_for_user(current_user))
```

**Broken Authentication**
```python
# ❌ VULNERABLE - Weak authentication
@app.post("/api/login")
def login(username: str, password: str):
    user = db.query(f"SELECT * FROM users WHERE username='{username}'")
    if user and user.password == password:  # Plain text comparison!
        return jsonify({"token": generate_token(user)})

# ✅ SECURE - Proper authentication
@app.post("/api/login")
def login(username: str, password: str):
    user = db.execute("SELECT * FROM users WHERE username=?", (username,))
    if user and bcrypt.checkpw(password.encode(), user.password_hash):
        return jsonify({"token": generate_jwt_token(user)})
    return jsonify({"error": "Invalid credentials"}), 401
```

**No Authorization Check**
```python
# ❌ VULNERABLE - Authenticated but no authorization
@app.delete("/api/resources/{id}")
def delete_resource(id: str):
    db.delete(id)  # Any authenticated user can delete!

# ✅ SECURE - Role-based authorization
@app.delete("/api/resources/{id}")
@auth_required
def delete_resource(id: str):
    current_user = get_current_user()
    resource = db.get(id)
    if resource.owner_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Forbidden"}), 403
    db.delete(id)
    return jsonify({"success": True})
```

### 2. Input Validation

**No Input Validation**
```python
# ❌ VULNERABLE - No validation
@app.post("/api/users")
def create_user(user_data: dict):
    return db.create_user(**user_data)  # Any data accepted!

# ✅ SECURE - Schema validation
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr
    age: int = Field(..., ge=0, le=150)

@app.post("/api/users")
def create_user(user_data: UserCreate):
    return db.create_user(**user_data.dict())
```

**SQL Injection**
```python
# ❌ VULNERABLE - SQL injection
@app.get("/api/users/{user_id}")
def get_user(user_id: str):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return db.execute(query)  # Injection if user_id = "1' OR '1'='1"

# ✅ SECURE - Parameterized queries
@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

### 3. Output Encoding

**JSON Injection**
```python
# ❌ VULNERABLE - Unescaped output
@app.get("/api/data")
def get_data():
    data = {"output": "<script>alert('XSS')</script>"}
    return jsonify(data)  # If client doesn't handle properly...

# ✅ SECURE - Proper encoding and Content-Type
@app.get("/api/data")
def get_data():
    data = {"output": html.escape("<script>alert('XSS')</script>")}
    response = jsonify(data)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response
```

### 4. Rate Limiting

**No Rate Limiting**
```python
# ❌ BAD - No rate limit, can be abused
@app.post("/api/send-email")
def send_email(to: str, subject: str, body: str):
    send_email_service(to, subject, body)  # Can be spammed!

# ✅ SECURE - Rate limiting
from flask_limiter import Limiter
limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.post("/api/send-email")
@limiter.limit("10/minute")
def send_email(to: str, subject: str, body: str):
    send_email_service(to, subject, body)
```

### 5. CORS Configuration

**Overly Permissive CORS**
```python
# ❌ VULNERABLE - Allows any origin
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

# ✅ SECURE - Specific origins
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in ['https://app.example.com', 'https://admin.example.com']:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response
```

### 6. Security Headers

**Missing Security Headers**
```python
# ❌ BAD - No security headers

# ✅ SECURE - Add security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response
```

### 7. Error Handling

**Information Disclosure**
```python
# ❌ BAD - Exposes sensitive information
@app.errorhandler(Exception)
def handle_error(e):
    return jsonify({
        "error": str(e),
        "traceback": traceback.format_exc()  # Exposes internals!
    }), 500

# ✅ SECURE - Generic error message
@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled exception: {e}")
    return jsonify({"error": "Internal server error"}), 500
```

### 8. API Key Management

**API Keys in URL**
```python
# ❌ BAD - API key in URL (visible in logs)
@app.get("/api/data")
def get_data():
    api_key = request.args.get('api_key')
    if validate_api_key(api_key):
        return get_sensitive_data()

# ✅ SECURE - API key in header
@app.get("/api/data")
def get_data():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not validate_api_key(api_key):
        return jsonify({"error": "Unauthorized"}), 401
    return get_sensitive_data()
```

**Hardcoded API Keys**
```python
# ❌ BAD - Hardcoded keys
API_KEYS = ["key123", "key456"]

# ✅ SECURE - Environment variable
import os
API_KEYS = os.getenv('API_KEYS', '').split(',')
```

### 9. Token Security

**Weak Token Generation**
```python
# ❌ BAD - Predictable tokens
import time
token = str(int(time.time()))  # Easy to guess!

# ✅ SECURE - Cryptographically secure
import secrets
token = secrets.token_urlsafe(32)
```

**No Token Expiration**
```python
# ❌ BAD - Tokens never expire
def generate_token(user_id):
    return jwt.encode({"user_id": user_id}, SECRET_KEY)  # No exp claim!

# ✅ SECURE - Token with expiration
def generate_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, SECRET_KEY)
```

### 10. Mass Assignment

**No Field Filtering**
```python
# ❌ VULNERABLE - Mass assignment
@app.put("/api/users/{id}")
def update_user(id: str, user_data: dict):
    # User can send is_admin=True and become admin!
    return db.update_user(id, **user_data)

# ✅ SECURE - Whitelist allowed fields
@app.put("/api/users/{id}")
def update_user(id: str, user_data: dict):
    allowed_fields = {'username', 'email', 'bio'}
    update_data = {k: v for k, v in user_data.items() if k in allowed_fields}
    return db.update_user(id, **update_data)
```

### 11. Pagination & Limiting

**No Pagination**
```python
# ❌ BAD - Returns all records (DoS risk)
@app.get("/api/users")
def get_users():
    return jsonify(db.get_all_users())  # Could be millions!

# ✅ SECURE - Paginated with limit
@app.get("/api/users")
def get_users(page: int = 1, per_page: int = 10):
    per_page = min(per_page, 100)  # Max 100 per page
    return jsonify(db.get_users(page=page, per_page=per_page))
```

### 12. File Uploads

**Unrestricted File Uploads**
```python
# ❌ VULNERABLE - Any file uploaded
@app.post("/api/upload")
def upload_file(file):
    file.save(f"/uploads/{file.filename}")  # Malicious files!

# ✅ SECURE - Validate uploads
@app.post("/api/upload")
def upload_file(file):
    # Validate file type
    if not file.content_type.startswith('image/'):
        return jsonify({"error": "Only images allowed"}), 400

    # Validate file size
    if file.content_length > 5 * 1024 * 1024:  # 5MB
        return jsonify({"error": "File too large"}), 400

    # Sanitize filename
    safe_filename = secure_filename(file.filename)

    # Save with restricted permissions
    filepath = f"/uploads/{safe_filename}"
    file.save(filepath)
    os.chmod(filepath, 0o644)  # Read-only for owner
    return jsonify({"path": safe_filename})
```

### 13. HTTP Methods

**Unsafe Method Handling**
```python
# ❌ BAD - GET requests modify data
@app.get("/api/delete/{id}")
def delete_item(id: str):
    db.delete(id)  # CSRF vulnerable!

# ✅ SECURE - Use proper methods
@app.delete("/api/items/{id}")
@csrf_protect
def delete_item(id: str):
    db.delete(id)
```

### 14. API Versioning

**No API Versioning**
```python
# ❌ BAD - Breaking changes affect all clients
@app.get("/api/users")
def get_users():
    return jsonify(db.get_users())

# ✅ GOOD - Versioned API
@app.get("/api/v1/users")
def get_users_v1():
    return jsonify(db.get_users_v1())

@app.get("/api/v2/users")
def get_users_v2():
    return jsonify(db.get_users_v2())  # Enhanced version
```

### 15. Logging & Monitoring

**No Security Logging**
```python
# ❌ BAD - No security event logging
@app.post("/api/login")
def login(username, password):
    if authenticate(username, password):
        return jsonify({"token": generate_token()})

# ✅ SECURE - Security event logging
@app.post("/api/login")
def login(username, password):
    if authenticate(username, password):
        logger.info(f"User logged in: {username}", extra={
            "event": "login_success",
            "username": username,
            "ip": request.remote_addr
        })
        return jsonify({"token": generate_token()})
    else:
        logger.warning(f"Failed login attempt: {username}", extra={
            "event": "login_failed",
            "username": username,
            "ip": request.remote_addr
        })
        return jsonify({"error": "Invalid credentials"}), 401
```

## Review Checklist

For each API endpoint, check:

- [ ] Authentication required for protected resources
- [ ] Strong authentication (bcrypt, JWT)
- [ ] Authorization checks for role-based access
- [ ] Input validation with schema enforcement
- [ ] SQL injection prevention (parameterized queries)
- [ ] Proper output encoding and Content-Type
- [ ] Rate limiting on expensive operations
- [ ] CORS configured for specific origins
- [ ] Security headers configured
- [ ] Generic error messages (no information disclosure)
- [ ] API keys in headers, not URL parameters
- [ ] Secrets not hardcoded
- [ ] Cryptographically secure token generation
- [ ] Tokens have expiration
- [ ] Mass assignment protection
- [ ] Pagination with reasonable limits
- [ ] File uploads validated and sanitized
- [ ] Proper HTTP methods (no GET for state changes)
- [ ] API versioning implemented
- [ ] Security event logging

## Output Format

```markdown
## API Security Review: [endpoint_name]

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
