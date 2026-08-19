# Python-Specific Security Review Skill

Review Python code for Python-specific security vulnerabilities and best practices.

## What to Check

### 1. String Injection & Format Strings

**Format String Injection**
```python
# ❌ VULNERABLE - User input in format string
user_input = "{__import__('os').system('rm -rf /')}"
print(user_input.format())  # Code execution!

# ✅ SECURE - Use f-strings or safe formatting
print(f"{user_input}")  # f-strings are safe
print("{}".format(user_input))  # Safe
print("%s" % user_input)  # Safe
```

**Unsafe Template Rendering**
```python
# ❌ VULNERABLE - Jinja2 without autoescape
from jinja2 import Environment
env = Environment()
template = env.from_string("Hello {{ name }}")
print(template.render(name=user_input))  # XSS vulnerability!

# ✅ SECURE - Autoescape enabled
from jinja2 import Environment, select_autoescape
env = Environment(autoescape=select_autoescape(['html', 'xml']))
template = env.from_string("Hello {{ name }}")
print(template.render(name=user_input))
```

### 2. Pickle/PyYAML Vulnerabilities

**Pickle Deserialization**
```python
# ❌ VULNERABLE - Arbitrary code execution
import pickle
data = pickle.loads(user_input)  # Can execute arbitrary code!

# ✅ SECURE - Use JSON or other safe formats
import json
data = json.loads(user_input)
```

**PyYAML Unsafe Load**
```python
# ❌ VULNERABLE - Arbitrary code execution
import yaml
data = yaml.load(user_input)  # Can execute arbitrary Python objects!

# ✅ SECURE - Use safe_load
data = yaml.safe_load(user_input)
```

### 3. Tempfile Security

**Insecure Tempfile Creation**
```python
# ❌ VULNERABLE - Race condition
import os
temp_path = "/tmp/tempfile.dat"  # Predictable path
with open(temp_path, "w") as f:  # Race condition
    f.write(sensitive_data)

# ✅ SECURE - Use tempfile module
import tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=True) as f:
    f.write(sensitive_data)
    # File automatically deleted
```

**Permission Issues**
```python
# ❌ BAD - Default permissions readable by all
with open('/tmp/data.txt', 'w') as f:
    f.write(sensitive_data)  # World-readable!

# ✅ SECURE - Set restrictive permissions
import os
import tempfile

fd, path = tempfile.mkstemp()
os.fchmod(fd, 0o600)  # Only owner can read/write
with os.fdopen(fd, 'w') as f:
    f.write(sensitive_data)
```

### 4. Subprocess Security

**Shell=True Injection**
```python
# ❌ VULNERABLE - Command injection
import subprocess
user_input = "; rm -rf /"
subprocess.run(f"ls {user_input}", shell=True)  # Dangerous!

# ✅ SECURE - Use list without shell
subprocess.run(["ls", user_input])  # Safe

# Or if shell needed:
subprocess.run(f"ls {shlex.quote(user_input)}", shell=True)
```

**Unsafe Shell Commands**
```python
# ❌ VULNERABLE - Direct shell access
import os
os.system(f"process {user_input}")  # Command injection!

# ✅ SECURE - Use subprocess with list
subprocess.run(["process", user_input], check=True)
```

### 5. SSL/TLS Issues

**Disabled Certificate Verification**
```python
# ❌ VULNERABLE - MITM attacks
import urllib.request
import ssl
context = ssl._create_unverified_context()
urllib.request.urlopen(url, context=context)  # No cert verification!

# ✅ SECURE - Verify certificates
import urllib.request
urllib.request.urlopen(url)  # Default verifies certificates
```

**Insecure Requests**
```python
# ❌ VULNERABLE - No verification
import requests
requests.get(url, verify=False)  # MITM vulnerability!

# ✅ SECURE - Verify certificates
requests.get(url)  # Default verifies
requests.get(url, verify='/path/to/ca-bundle.crt')
```

### 6. Cryptography

**Weak Encryption**
```python
# ❌ VULNERABLE - Weak algorithms
from Crypto.Cipher import DES
cipher = DES.new(key, DES.MODE_ECB)  # DES is broken, ECB is weak

# ✅ SECURE - Strong algorithms
from cryptography.fernet import Fernet
key = Fernet.generate_key()
cipher = Fernet(key)
encrypted = cipher.encrypt(data)
```

**Hardcoded Keys**
```python
# ❌ VULNERABLE - Hardcoded key
SECRET_KEY = b'not-secure-at-all'

# ✅ SECURE - From environment
import os
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError('SECRET_KEY required')
```

**Random Number Generation**
```python
# ❌ BAD - Predictable for security purposes
import random
secure_token = random.random()  # Not cryptographically secure!

# ✅ SECURE - Cryptographically secure random
import secrets
secure_token = secrets.token_urlsafe(32)
```

### 7. File Operations

**Path Traversal**
```python
# ❌ VULNERABLE - Path traversal attack
filename = user_input  # Could be "../../etc/passwd"
with open(f'/uploads/{filename}', 'r') as f:
    return f.read()

# ✅ SECURE - Validate and sanitize
import os
filename = os.path.basename(user_input)  # Remove directory
if not filename.isalnum():
    raise ValueError('Invalid filename')
safe_path = os.path.join('/uploads', filename)
with open(safe_path, 'r') as f:
    return f.read()
```

**Race Conditions (TOCTOU)**
```python
# ❌ VULNERABLE - Time-of-check to time-of-use
if os.path.exists(path):
    with open(path, 'r') as f:  # Path may change between check and use
        return f.read()

# ✅ SECURE - Open directly and handle errors
try:
    with open(path, 'r') as f:
        return f.read()
except FileNotFoundError:
    return None
```

### 8. Authentication & Sessions

**Insecure Session Generation**
```python
# ❌ BAD - Predictable session IDs
import time
session_id = str(int(time.time()))  # Easy to guess!

# ✅ SECURE - Cryptographically secure
import secrets
session_id = secrets.token_hex(32)
```

**Password Handling**
```python
# ❌ VULNERABLE - Plain text passwords
passwords = {'user': 'password123'}  # Stored in plain text!

# ✅ SECURE - Hashed passwords
import bcrypt
password_hash = bcrypt.hashpw(password, bcrypt.gensalt())
# Verify with bcrypt.checkpw(password, password_hash)
```

### 9. Logging & Debugging

**Logging Sensitive Data**
```python
# ❌ BAD - Logging secrets
logger.info(f"User login: {username} {password}")
logger.debug(f"API request: {request.json()}")

# ✅ SECURE - Avoid sensitive data
logger.info(f"User login: {username}")
# Never log passwords, tokens, SSNs, credit cards
```

**Debug Mode in Production**
```python
# ❌ BAD - Debug mode exposes sensitive information
app.run(debug=True)  # Shows stack traces, variables

# ✅ SECURE - Debug only in development
DEBUG = os.getenv('DEBUG') == 'true'
app.run(debug=DEBUG)
```

### 10. Type Safety & Injection

**SQL Injection**
```python
# ❌ VULNERABLE - String concatenation
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# ✅ SECURE - Parameterized queries
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

**NoSQL Injection**
```python
# ❌ VULNERABLE - MongoDB injection
query = {"username": user_input}  # If user_input contains operators
db.users.find(query)

# ✅ SECURE - Validate input first
import re
if not re.match(r'^[a-zA-Z0-9_]+$', user_input):
    raise ValueError('Invalid username')
query = {"username": user_input}
db.users.find(query)
```

### 11. Dependency Security

**Vulnerable Dependencies**
```python
# ❌ BAD - Outdated vulnerable packages
# requirements.txt:
# flask==0.11  # Old version with vulnerabilities

# ✅ SECURE - Keep dependencies updated
# requirements.txt:
# flask==3.0.0  # Latest stable
# Regularly run: pip-audit, safety check
```

### 12. Configuration Security

**Environment Variables for Secrets**
```python
# ✅ GOOD - Use environment variables
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('API_KEY')
if not api_key:
    raise ValueError('API_KEY must be set')
```

**Missing Input Validation**
```python
# ❌ BAD - No validation
@app.post('/users')
def create_user(user: dict):
    # Direct use of user input
    db.insert(user)

# ✅ SECURE - Validate with Pydantic
from pydantic import BaseModel, validator

class User(BaseModel):
    username: str
    email: str

    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v

    @validator('email')
    def email_valid(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v
```

## Review Checklist

For each Python file, check:

- [ ] No format string injection vulnerabilities
- [ ] Safe template rendering with autoescape
- [ ] No pickle deserialization of untrusted data
- [ ] PyYAML safe_load instead of load
- [ ] Secure temp file creation with proper permissions
- [ ] Subprocess calls avoid shell=True when possible
- [ ] SSL/TLS certificate verification enabled
- [ ] Strong cryptographic algorithms used
- [ ] No hardcoded secrets or keys
- [ ] Cryptographically secure random generation
- [ ] Path traversal protection
- [ ] Race condition (TOCTOU) prevention
- [ ] Secure session generation
- [ ] Passwords properly hashed
- [ ] No sensitive data in logs
- [ ] Debug mode only in development
- [ ] Parameterized database queries
- [ ] Input validation and sanitization
- [ ] Dependencies up to date and secure

## Output Format

```markdown
## Python Security Review: [file_name]

### Critical
- [Issue] - [CVE/Security impact] - [Recommendation]

### High
- [Issue] - [Security impact] - [Recommendation]

### Medium
- [Issue] - [Security impact] - [Recommendation]

### Low
- [Issue] - [Security impact] - [Recommendation]

### Positive Patterns
+ [Good security practice found]
```
