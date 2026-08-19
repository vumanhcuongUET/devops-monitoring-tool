# Database Security Review Skill

Review database operations, configurations, and queries for security vulnerabilities and best practices.

## What to Check

### 1. SQL Injection Prevention

**String Concatenation**
```python
# ❌ VULNERABLE - SQL injection
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# ✅ SECURE - Parameterized queries
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))
```

**ORM Without Validation**
```python
# ❌ VULNERABLE - Raw SQL in ORM
User.objects.raw(f"SELECT * FROM users WHERE name = '{username}'")

# ✅ SECURE - ORM methods with parameterization
User.objects.filter(username=username)
# Or if raw needed:
User.objects.raw("SELECT * FROM users WHERE name = %s", [username])
```

### 2. Authentication & Access Control

**Weak Password Storage**
```python
# ❌ VULNERABLE - Plain text passwords
query = "INSERT INTO users (username, password) VALUES (%s, %s)"
cursor.execute(query, (username, password))

# ✅ SECURE - Hashed passwords
import bcrypt
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
query = "INSERT INTO users (username, password_hash) VALUES (%s, %s)"
cursor.execute(query, (username, password_hash))
```

**Overprivileged Database Users**
```sql
-- ❌ VULNERABLE - App runs as DBA
GRANT ALL PRIVILEGES ON *.* TO 'appuser'@'%';

-- ✅ SECURE - Least privilege
GRANT SELECT, INSERT, UPDATE, DELETE ON myapp.* TO 'appuser'@'appserver';
REVOKE ALL PRIVILEGES ON *.* FROM 'appuser'@'%';
```

### 3. Connection Security

**Unencrypted Connections**
```python
# ❌ VULNERABLE - Plain text connection
engine = create_engine('postgresql://user:pass@host/db')

# ✅ SECURE - SSL required
engine = create_engine(
    'postgresql://user:pass@host/db',
    connect_args={'sslmode': 'require'}
)
```

**Connection String Exposure**
```python
# ❌ BAD - Connection string in code
DATABASE_URL = "postgresql://user:pass@host/db"

# ✅ SECURE - Environment variable
import os
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError('DATABASE_URL required')
```

### 4. Input Validation

**Type Validation**
```python
# ❌ BAD - No type validation
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return execute(query)

# ✅ SECURE - Type validation + parameterization
def get_user(user_id: int):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError('Invalid user ID')
    query = "SELECT * FROM users WHERE id = %s"
    return execute(query, (user_id,))
```

**Length Validation**
```python
# ❌ BAD - No length limits
def search_users(name: str):
    query = f"SELECT * FROM users WHERE name LIKE '%{name}%'"
    return execute(query)

# ✅ SECURE - Length limit + parameterization
def search_users(name: str):
    if len(name) > 100:
        raise ValueError('Search term too long')
    query = "SELECT * FROM users WHERE name LIKE %s"
    return execute(query, (f'%{name}%',))
```

### 5. Error Handling

**Information Disclosure**
```python
# ❌ BAD - Exposes database internals
try:
    result = execute_query(query)
except Exception as e:
    return {"error": str(e), "query": query}  # Leaks schema!

# ✅ SECURE - Generic error
try:
    result = execute_query(query)
except Exception as e:
    logger.error(f"Database error: {e}")
    return {"error": "Database operation failed"}
```

### 6. Query Performance & DoS

**No Query Limits**
```python
# ❌ BAD - Can return millions of rows
def get_all_users():
    return execute("SELECT * FROM users")

# ✅ SECURE - Pagination
def get_users(page: int = 0, limit: int = 100):
    limit = min(limit, 1000)  # Max 1000 per page
    offset = page * limit
    return execute(
        "SELECT * FROM users LIMIT %s OFFSET %s",
        (limit, offset)
    )
```

**Missing Indexes**
```sql
-- ❌ BAD - Full table scans
SELECT * FROM users WHERE email = 'user@example.com';
-- Without index on email, scans entire table

-- ✅ GOOD - Indexed queries
CREATE INDEX idx_users_email ON users(email);
SELECT * FROM users WHERE email = 'user@example.com';
```

### 7. Data Encryption

**Unencrypted Sensitive Data**
```sql
-- ❌ VULNERABLE - Sensitive data in plain text
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    ssn VARCHAR(11)  -- Social Security Number in plain text!
);

-- ✅ SECURE - Encrypted columns
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    ssn_encrypted TEXT  -- Encrypted SSN
);
-- Encrypt at application level before storing
```

**Encryption at Rest**
```sql
-- ✅ GOOD - Enable encryption
-- PostgreSQL: Use pgcrypto extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt data
INSERT INTO users (email, ssn_encrypted)
VALUES ('user@example.com', pgp_sym_encrypt('123-45-6789', 'encryption_key'));

-- Decrypt data
SELECT pgp_sym_decrypt(ssn_encrypted::bytea, 'encryption_key') FROM users;
```

### 8. Database Configuration

**Default Credentials**
```sql
-- ❌ VULNERABLE - Default passwords
-- postgres user with default password

-- ✅ SECURE - Change defaults
ALTER USER postgres WITH PASSWORD 'strong_password_here';
```

**Public Access**
```sql
-- ❌ VULNERABLE - Access from anywhere
-- pg_hba.conf:
# host all all 0.0.0.0/0 md5

-- ✅ SECURE - Restricted access
-- pg_hba.conf:
host all all 10.0.0.0/8 md5  -- Only internal network
hostssl all all 0.0.0.0/0 md5  -- Require SSL for external
```

### 9. Backup Security

**Unencrypted Backups**
```bash
# ❌ BAD - Plain text backups
pg_dump mydb > backup.sql

# ✅ GOOD - Encrypted backups
pg_dump mydb | gzip | gpg --encrypt --recipient admin@example.com > backup.sql.gz.gpg
```

**Backup Access Control**
```bash
# ❌ BAD - World-readable backups
chmod 644 backup.sql

# ✅ GOOD - Restricted access
chmod 600 backup.sql
chown dbadmin:dbadmin backup.sql
```

### 10. Data Retention

**Infinite Data Retention**
```python
# ❌ BAD - Data never deleted
def log_action(user_id, action):
    execute("INSERT INTO audit_log (user_id, action) VALUES (%s, %s)",
            (user_id, action))

# ✅ GOOD - Data retention policy
def log_action(user_id, action):
    execute("INSERT INTO audit_log (user_id, action) VALUES (%s, %s)",
            (user_id, action))
    # Clean old logs (90 days)
    execute("DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL '90 days'")
```

### 11. Connection Pooling

**Connection Leaks**
```python
# ❌ BAD - Connections not closed
def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()  # Connection never closed!

# ✅ GOOD - Proper cleanup
def get_user(user_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        conn.close()  # Always closed
```

**Or use context manager:**
```python
# ✅ BEST - Context manager
def get_user(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
```

### 12. Transaction Management

**Missing Rollback on Error**
```python
# ❌ BAD - No error handling
def transfer_money(from_account, to_account, amount):
    execute(f"UPDATE accounts SET balance = balance - {amount} WHERE id = {from_account}")
    execute(f"UPDATE accounts SET balance = balance + {amount} WHERE id = {to_account}")

# ✅ SECURE - Transaction with rollback
def transfer_money(from_account, to_account, amount):
    try:
        execute("BEGIN")
        execute("UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (amount, from_account))
        execute("UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (amount, to_account))
        execute("COMMIT")
    except Exception as e:
        execute("ROLLBACK")
        raise e
```

### 13. Database Auditing

**No Audit Trail**
```sql
-- ❌ BAD - No audit logging
-- Changes not tracked

-- ✅ GOOD - Audit triggers
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(255),
    operation VARCHAR(10),
    old_data JSONB,
    new_data JSONB,
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by VARCHAR(255)
);

CREATE TRIGGER audit_users
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION audit_trigger();
```

### 14. Schema Security

**Public Schema**
```sql
-- ❌ BAD - Tables in public schema
CREATE TABLE users (...);  -- In public schema

-- ✅ GOOD - Separate schema
CREATE SCHEMA app_data;
CREATE TABLE app_data.users (...);

-- Revoke public access
REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

### 15. Migration Safety

**Unsafe Migrations**
```python
# ❌ BAD - Destructive without backup
def migrate():
    execute("DROP TABLE users")  # Data loss!

# ✅ GOOD - Safe migration
def migrate():
    # Backup first
    execute("CREATE TABLE users_backup AS SELECT * FROM users")
    # Verify backup
    if execute("SELECT COUNT(*) FROM users_backup")[0] > 0:
        execute("DROP TABLE users")
    else:
        raise Exception("Backup failed, aborting migration")
```

## Review Checklist

For each database operation, check:

- [ ] SQL injection prevention (parameterized queries)
- [ ] Passwords hashed (bcrypt, argon2)
- [ ] Database users follow least privilege
- [ ] Connections use SSL/TLS
- [ ] Connection strings from environment variables
- [ ] Input type and length validation
- [ ] Generic error messages (no information disclosure)
- [ ] Query limits and pagination
- [ ] Appropriate indexes for performance
- [ ] Sensitive data encrypted at rest
- [ ] No default credentials
- [ ] Restricted network access
- [ ] Backups encrypted and access-controlled
- [ ] Data retention policies implemented
- [ ] Proper connection cleanup (context managers)
- [ ] Transaction management with rollback
- [ ] Audit logging for sensitive operations
- [ ] Separate schemas for different applications
- [ ] Safe migration practices with backups

## Output Format

```markdown
## Database Security Review: [query/function/file]

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
