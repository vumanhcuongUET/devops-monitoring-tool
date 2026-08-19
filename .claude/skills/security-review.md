# Security Review Skill

Review code for critical security vulnerabilities and provide remediation guidance.

## What to Check

### 1. Injection Vulnerabilities

**SQL Injection**
```python
# ❌ VULNERABLE
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# ✅ SECURE
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))
```

**Command Injection**
```python
# ❌ VULNERABLE
os.system(f"kubectl delete pod {pod_name}")

# ✅ SECURE
subprocess.run(['kubectl', 'delete', 'pod', pod_name], check=True)
```

**Template Injection (Jinja2)**
```python
# ❌ VULNERABLE
template.render(user_input=user_data)

# ✅ SECURE
template.render(user_input=escape(user_data))
```

### 2. Authentication & Authorization

**Missing Authorization Check**
```python
# ❌ VULNERABLE - No auth check
@app.delete("/api/resources/{id}")
async def delete_resource(id: str):
    await db.delete(id)
    return {"success": True}

# ✅ SECURE
@app.delete("/api/resources/{id}")
async def delete_resource(id: str, user: User = Depends(get_current_user)):
    if not user.can_delete():
        raise HTTPException(403)
    await db.delete(id)
```

**Broken Access Control**
```python
# ❌ VULNERABLE - Direct object reference
@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    return await db.get_user(user_id)  # Anyone can access any user

# ✅ SECURE
@app.get("/api/users/{user_id}")
async def get_user(user_id: str, current_user: User = Depends(get_current_user)):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(403)
    return await db.get_user(user_id)
```

### 3. Secrets Management

**Hardcoded Secrets**
```python
# ❌ VULNERABLE
API_KEY = "sk-1234567890abcdef"
DB_PASSWORD = "password123"

# ✅ SECURE
API_KEY = os.getenv("API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not API_KEY:
    raise ValueError("API_KEY required")
```

**Secrets in Code**
```yaml
# ❌ VULNERABLE
apiVersion: v1
kind: Secret
metadata:
  name: api-secret
stringData:
  password: "hardcoded-password"

# ✅ SECURE - Use sealed-secrets or external secret manager
```

### 4. Input Validation

**Missing Input Validation**
```python
# ❌ VULNERABLE
@app.post("/api/execute")
async def execute(command: str):
    result = subprocess.run(command, shell=True)
    return result

# ✅ SECURE
@app.post("/api/execute")
async def execute(command: ValidatedCommand):
    if not command.is_safe():
        raise HTTPException(400, "Invalid command")
    result = subprocess.run(command.get_safe_args())
    return result
```

**Path Traversal**
```python
# ❌ VULNERABLE
filename = request.args.get('file')
with open(f'/uploads/{filename}', 'r') as f:
    return f.read()

# ✅ SECURE
filename = request.args.get('file')
if not is_safe_filename(filename):
    raise HTTPException(400)
safe_path = os.path.join('/uploads', os.path.basename(filename))
with open(safe_path, 'r') as f:
    return f.read()
```

### 5. Cryptography

**Weak Encryption**
```python
# ❌ VULNERABLE
encrypted = encrypt(data, key, mode='ECB')  # ECB is weak

# ✅ SECURE
encrypted = encrypt(data, key, mode='AES-GCM')  # Authenticated encryption
```

**Hardcoded Keys**
```python
# ❌ VULNERABLE
SECRET_KEY = b'fixed-secret-key-12345'

# ✅ SECURE
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError('SECRET_KEY required')
```

**Missing Signature Verification**
```python
# ❌ VULNERABLE - No signature check
webhook_data = json.loads(request.body)

# ✅ SECURE
signature = request.headers.get('X-Signature')
if not verify_signature(request.body, signature):
    raise HTTPException(401, 'Invalid signature')
webhook_data = json.loads(request.body)
```

### 6. Security Headers

**Missing Security Headers**
```python
# ✅ SECURE - Add security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

### 7. Logging Sensitive Data

**Logging Secrets**
```python
# ❌ VULNERABLE
logger.info(f"User logged in: {user.email} {user.password}")

# ✅ SECURE
logger.info(f"User logged in: {user.email}")
# Never log passwords, tokens, or secrets
```

### 8. Dependency Security

**Vulnerable Dependencies**
```bash
# ✅ SECURE - Regular dependency checks
npm audit
pip-audit
snyk test
```

## Review Checklist

For each code change, check:

- [ ] No SQL injection vectors
- [ ] No command injection possibilities
- [ ] All user inputs are validated and sanitized
- [ ] Authentication/authorization is properly implemented
- [ ] No hardcoded secrets or credentials
- [ ] No insecure direct object references (IDOR)
- [ ] Proper error handling without exposing sensitive info
- [ ] Security headers are configured
- [ ] Secrets are not logged
- [ ] Dependencies are up to date and secure
- [ ] Cryptographic functions are used correctly
- [ ] File uploads are validated and secured

## Output Format

Report findings in this format:

```markdown
## Security Review: [file_name]

### Critical
- [Issue] - [Remediation]

### High
- [Issue] - [Remediation]

### Medium
- [Issue] - [Remediation]

### Low
- [Issue] - [Remediation]
```
