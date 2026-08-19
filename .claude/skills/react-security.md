# React/TypeScript Security Review Skill

Review React and TypeScript code for frontend security vulnerabilities and best practices.

## What to Check

### 1. XSS Prevention

**DangerouslySetInnerHTML**
```tsx
// ❌ VULNERABLE - XSS attack
function UserContent({ content }: { content: string }) {
  return <div dangerouslySetInnerHTML={{ __html: content }} />;
}
// If content = "<script>alert('XSS')</script>", script executes!

// ✅ SECURE - Use DOMPurify or text content
import DOMPurify from 'dompurify';

function UserContent({ content }: { content: string }) {
  const clean = DOMPurify.sanitize(content);
  return <div dangerouslySetInnerHTML={{ __html: clean }} />;
}
// Or just: return <div>{content}</div>;
```

**User Input in Attributes**
```tsx
// ❌ VULNERABLE - XSS via attributes
function UserLink({ href }: { href: string }) {
  return <a href={href}>Click</a>;
}
// If href = "javascript:alert('XSS')", executes script!

// ✅ SECURE - Validate URLs
function UserLink({ href }: { href: string }) {
  if (!href.match(/^https?:\/\//)) {
    return null; // Reject non-HTTP URLs
  }
  return <a href={href}>Click</a>;
}
```

### 2. State Management & Secrets

**Secrets in Client-Side Code**
```tsx
// ❌ VULNERABLE - API keys in client code
const API_KEY = "sk-1234567890abcdef";
fetch(`/api/data?key=${API_KEY}`);

// ✅ SECURE - Backend proxy
const response = await fetch('/api/data', {
  headers: {
    'Authorization': `Bearer ${token}` // Token from secure storage
  }
});
// Backend validates token and makes API call
```

**Sensitive Data in State/LocalStorage**
```tsx
// ❌ BAD - Sensitive data in localStorage
localStorage.setItem('token', token);
localStorage.setItem('user', JSON.stringify(user));

// ✅ SECURE - Use secure storage
// Use httpOnly cookies or secure session storage
// Or use secure libraries like:
import { SecureStorage } from 'secure-web-storage';
```

### 3. Authentication & Session

**Insecure Token Storage**
```tsx
// ❌ BAD - Token in localStorage (accessible by XSS)
localStorage.setItem('authToken', token);

// ✅ SECURE - httpOnly cookie
// Set by backend: Set-Cookie: token=xxx; HttpOnly; Secure; SameSite=Strict
// Frontend just includes cookie automatically

// Or use secure memory-only storage
function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  // Token lost on refresh (need re-auth)
  // But secure against XSS
}
```

**No Token Expiration Check**
```tsx
// ❌ BAD - No expiration check
function useApi() {
  const token = localStorage.getItem('token');
  // Used without checking expiration!

  // ✅ SECURE - Check expiration
  function isTokenExpired(token: string): boolean {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return Date.now() >= payload.exp * 1000;
  }

  if (token && isTokenExpired(token)) {
    logout();
    return null;
  }
}
```

### 4. Input Validation

**Client-Side Only Validation**
```tsx
// ❌ BAD - Only client validation
function LoginForm() {
  const [email, setEmail] = useState('');
  const handleSubmit = () => {
    if (email.includes('@')) {  // Only client check!
      submit(email);
    }
  };
}

// ✅ SECURE - Client + Server validation
function LoginForm() {
  const handleSubmit = async () => {
    try {
      await api.login({ email }); // Server validates too
    } catch (error) {
      setError('Invalid email');
    }
  };
}
```

**No Output Encoding**
```tsx
// ❌ VULNERABLE - Unescaped output
function UserMessage({ message }: { message: string }) {
  return <div>{message}</div>; // React escapes by default
}

// But when using dangerouslySetInnerHTML or refs:
// ❌ VULNERABLE
function UserMessage({ message }: { message: string }) {
  const divRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (divRef.current) {
      divRef.current.innerHTML = message; // No escaping!
    }
  });
  return <div ref={divRef} />;
}

// ✅ SECURE
function UserMessage({ message }: { message: string }) {
  return <div>{message}</div>; // React auto-escapes
}
```

### 5. API Security

**CORS Issues**
```tsx
// ❌ BAD - API calls to different origins without CORS
fetch('https://api.example.com/data', {
  method: 'POST',
  credentials: 'include' // Sends cookies to different origin!
});

// ✅ SECURE - Same-origin or proper CORS
fetch('/api/data', { // Same origin (proxied)
  method: 'POST',
  credentials: 'same-origin'
});
```

**No CSRF Protection**
```tsx
// ✅ GOOD - CSRF token for state-changing operations
function DeleteButton() {
  const csrfToken = useCsrfToken();
  const handleDelete = async () => {
    await fetch('/api/resource', {
      method: 'DELETE',
      headers: {
        'X-CSRF-Token': csrfToken // Include CSRF token
      }
    });
  };
}
```

### 6. Third-Party Libraries

**Vulnerable Dependencies**
```json
// ❌ BAD - Outdated vulnerable packages
{
  "dependencies": {
    "react": "16.8.0", // Old version with vulnerabilities
    "axios": "0.19.0" // Known vulnerabilities
  }
}

// ✅ SECURE - Regular updates
{
  "dependencies": {
    "react": "^18.2.0", // Latest stable
    "axios": "^1.6.0"
  }
}
// Run: npm audit fix
```

### 7. Content Security Policy

**Missing CSP**
```tsx
// ❌ BAD - No Content Security Policy

// ✅ GOOD - CSP headers or meta tag
// In HTML:
// <meta http-equiv="Content-Security-Policy"
//   content="default-src 'self'; script-src 'self' 'unsafe-inline'">

// Or via backend headers:
// Content-Security-Policy: default-src 'self'; script-src 'self'
```

### 8. Error Handling

**Information Disclosure**
```tsx
// ❌ BAD - Exposes sensitive errors
function ApiCall() {
  const [error, setError] = useState<string>();
  const handleCall = async () => {
    try {
      await api.call();
    } catch (e) {
      setError((e as Error).stack || ''); // Exposes internals!
    }
  };
  return <div>{error}</div>;
}

// ✅ SECURE - Generic error messages
function ApiCall() {
  const [error, setError] = useState<string>();
  const handleCall = async () => {
    try {
      await api.call();
    } catch (e) {
      console.error('API error:', e); // Log to server
      setError('Operation failed. Please try again.');
    }
  };
}
```

### 9. URL Parameters & Routing

**URL Parameter Injection**
```tsx
// ❌ VULNERABLE - Unvalidated URL params
function UserProfile() {
  const { id } = useParams();
  // Direct use without validation!

  // ✅ SECURE - Validate params
  const { id } = useParams();
  if (!id || !/^[a-zA-Z0-9-]+$/.test(id)) {
    return <ErrorPage />;
  }
}
```

**Open Redirects**
```tsx
// ❌ VULNERABLE - Open redirect
function RedirectPage() {
  const { target } = useParams();
  window.location.href = target; // Redirects to any URL!

  // ✅ SECURE - Validate redirect targets
  const { target } = useParams();
  const allowedDomains = ['app.example.com', 'admin.example.com'];
  const url = new URL(target);
  if (allowedDomains.includes(url.hostname)) {
    window.location.href = target;
  }
}
```

### 10. TypeScript Security

**Unsafe Type Assertions**
```tsx
// ❌ BAD - Unsafe type assertion
function processUser(input: any) {
  const user = input as User; // No validation!
  return user.ssn; // May not exist or be invalid

  // ✅ SECURE - Runtime validation
  function isUser(input: any): input is User {
    return input && typeof input.ssn === 'string';
  }

  if (isUser(input)) {
    return input.ssn;
  }
}
```

### 11. State & Props Security

**Prop Drilling Secrets**
```tsx
// ❌ BAD - Secrets passed through props
function App() {
  const apiKey = "secret-key";
  return <ChildComponent apiKey={apiKey} />;
}

// ✅ SECURE - Secrets stay server-side
function App() {
  const fetchData = async () => {
    const response = await fetch('/api/data'); // Backend handles auth
    return response.json();
  };
}
```

### 12. WebSockets & Real-time

**Unvalidated WebSocket Messages**
```tsx
// ❌ BAD - Executing WebSocket messages directly
useEffect(() => {
  ws.onmessage = (event) => {
    const command = JSON.parse(event.data);
    eval(command.action); // Executes arbitrary code!
  };
});

// ✅ SECURE - Validate and sanitize
useEffect(() => {
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (isValidMessage(message)) {
      handleMessage(message);
    }
  };
});
```

### 13. Bundle & Build Security

**Production Source Maps**
```tsx
// ❌ BAD - Source maps in production
// vite.config.ts / webpack config:
// sourcemap: true  // Exposes source code!

// ✅ SECURE - No source maps in production
// sourcemap: false  // Or only for errors
```

### 14. Authentication Flow

**Token Leakage in URL**
```tsx
// ❌ BAD - Token in URL (visible in logs, history)
function LoginPage() {
  const handleLogin = async () => {
    const { token } = await api.login();
    window.location.href = `/dashboard?token=${token}`;
  };
}

// ✅ SECURE - Token in header or cookie
function LoginPage() {
  const handleLogin = async () => {
    await api.login();
    // Token stored in httpOnly cookie by backend
    window.location.href = '/dashboard';
  };
}
```

## Review Checklist

For each React/TypeScript file, check:

- [ ] No dangerouslySetInnerHTML without sanitization
- [ ] User input in attributes is validated
- [ ] No secrets (API keys, tokens) in client code
- [ ] Sensitive data not in localStorage/sessionStorage
- [ ] Token expiration checked
- [ ] Input validation on client AND server
- [ ] Proper CORS configuration
- [ ] CSRF protection for state-changing operations
- [ ] Dependencies up to date and secure
- [ ] Content Security Policy configured
- [ ] Error messages don't expose sensitive information
- [ ] URL parameters validated and sanitized
- [ ] No unsafe type assertions without validation
- [ ] Secrets not passed through props
- [ ] WebSocket messages validated
- [ ] No source maps in production
- [ ] Tokens not in URLs

## Output Format

```markdown
## React Security Review: [file_name]

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
