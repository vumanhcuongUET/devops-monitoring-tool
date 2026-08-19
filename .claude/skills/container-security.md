# Docker/Container Security Review Skill

Review Dockerfiles and container configurations for security vulnerabilities and best practices.

## What to Check

### 1. Base Image Security

**Using Vulnerable Base Images**
```dockerfile
# ❌ VULNERABLE - Outdated image with vulnerabilities
FROM node:10  # Old version with known vulnerabilities

# ✅ SECURE - Latest stable version
FROM node:20-alpine  # Regularly updated

# Or specify exact version
FROM node:20.11.0-alpine
```

**Using Distroless Images**
```dockerfile
# ✅ GOOD - Minimal attack surface
FROM gcr.io/distroless/nodejs20-debian12

# Instead of full OS
# FROM node:20  # Has package manager, shell, etc.
```

### 2. Root User

**Running as Root**
```dockerfile
# ❌ VULNERABLE - Container runs as root
FROM node:20
COPY app /app
WORKDIR /app
CMD ["node", "server.js"]  # Runs as root!

# ✅ SECURE - Non-root user
FROM node:20
COPY app /app
WORKDIR /app
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001
USER nodejs
CMD ["node", "server.js"]
```

### 3. Minimal Layers

**Too Many Layers**
```dockerfile
# ❌ BAD - Too many layers
RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y curl
RUN apt-get install -y git

# ✅ GOOD - Combined layers
RUN apt-get update && \
    apt-get install -y python3 curl git && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean
```

### 4. Secrets in Images

**Hardcoded Secrets**
```dockerfile
# ❌ VULNERABLE - Secrets in image
ENV API_KEY="sk-1234567890"
ENV DB_PASSWORD="password123"

# ✅ SECURE - Runtime secrets only
# No secrets in Dockerfile
# Use environment variables or secrets at runtime
docker run -e API_KEY=$API_KEY -e DB_PASSWORD=$DB_PASSWORD myapp
```

**Secrets in Build Arguments**
```dockerfile
# ⚠️ RISKY - Build args visible in image history
ARG API_KEY
ENV SECRET_API_KEY=$API_KEY  # Visible in docker inspect!

# ✅ SECURE - Use build-time only if needed, then remove
ARG API_KEY
# Use for build, don't persist to runtime
RUN curl -H "Authorization: Bearer ${API_KEY}" https://api.example.com/data
# Don't set ENV with secrets
```

### 5. Package Installation

**Unvalidated Packages**
```dockerfile
# ❌ BAD - Installing without verification
RUN npm install  # Could install malicious packages

# ✅ SECURE - Lock files and checksums
COPY package-lock.json package.json ./
RUN npm ci --production  # Uses lock file
```

**Installation Cleanup**
```dockerfile
# ❌ BAD - Package manager cache left behind
RUN apt-get update && apt-get install -y python3

# ✅ GOOD - Cache removed
RUN apt-get update && \
    apt-get install -y python3 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean
```

### 6. File Permissions

**World-Readable Secrets**
```dockerfile
# ❌ BAD - Secrets world-readable
COPY secrets.json /etc/secrets/

# ✅ GOOD - Restricted permissions
COPY secrets.json /etc/secrets/
RUN chmod 600 /etc/secrets/secrets.json
```

### 7. Image Size

**Bloated Images**
```dockerfile
# ❌ BAD - Unnecessary tools
FROM ubuntu:latest
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    vim \
    curl \
    wget
# Image > 500MB

# ✅ GOOD - Minimal image
FROM alpine:latest
RUN apk add --no-cache python3
# Image < 50MB
```

### 8. COPY vs ADD

**Using ADD**
```dockerfile
# ❌ BAD - ADD has hidden behaviors
ADD app.tar.gz /usr/src/app/  # Auto-extracts, can be dangerous
ADD http://example.com/file.sh /  # Downloads without verification

# ✅ GOOD - Use COPY for files, curl for downloads
COPY app.tar.gz /usr/src/app/
RUN tar -xzf /usr/src/app/app.tar.gz -C /usr/src/app

RUN curl -o /tmp/file.sh https://example.com/file.sh && \
    chmod +x /tmp/file.sh
```

### 9. Health Checks

**No Health Check**
```dockerfile
# ❌ BAD - No health check
FROM node:20
CMD ["node", "server.js"]

# ✅ GOOD - Health check defined
FROM node:20
COPY app /app
WORKDIR /app
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node healthcheck.js || exit 1
CMD ["node", "server.js"]
```

### 10. Multi-stage Builds

**Single Stage with Build Tools**
```dockerfile
# ❌ BAD - Build tools in final image
FROM golang:latest
COPY . /app
WORKDIR /app
RUN go build -o app .
# Image includes Go compiler, source, etc. > 800MB

# ✅ GOOD - Multi-stage build
FROM golang:latest AS builder
COPY . /app
WORKDIR /app
RUN go build -o app .

FROM alpine:latest
COPY --from=builder /app/app /usr/local/bin/app
# Final image < 20MB, only binary
```

### 11. Signing & Verification

**Unsigned Images**
```yaml
# ❌ BAD - Using unsigned images
spec:
  containers:
  - name: app
    image: myapp:latest

# ✅ GOOD - Signed and verified
# Before deployment:
# docker trust sign myapp:latest
# docker trust verify myapp:latest
```

### 12. Container Runtime Security

**Privileged Containers**
```yaml
# ❌ VULNERABLE - Privileged container
spec:
  containers:
  - name: app
    securityContext:
      privileged: true

# ✅ SECURE - No privileges
spec:
  containers:
  - name: app
    securityContext:
      privileged: false
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
        - ALL
```

**Host Path Mounts**
```yaml
# ❌ VULNERABLE - Host filesystem access
volumeMounts:
- name: host-root
  mountPath: /host
volumes:
- name: host-root
  hostPath:
    path: /  # Entire host filesystem!

# ✅ SECURE - Avoid hostPath or use specific paths
volumeMounts:
- name: config
  mountPath: /etc/config
  readOnly: true
volumes:
- name: config
  configMap:
    name: app-config
```

### 13. Resource Limits

**No Resource Limits**
```yaml
# ❌ BAD - Can consume all node resources
spec:
  containers:
  - name: app
    image: myapp:latest

# ✅ GOOD - Resource limits set
spec:
  containers:
  - name: app
    image: myapp:latest
    resources:
      requests:
        memory: "128Mi"
        cpu: "100m"
      limits:
        memory: "256Mi"
        cpu: "500m"
```

### 14. Network Security

**Host Network**
```yaml
# ❌ VULNERABLE - Host network namespace
spec:
  hostNetwork: true

# ✅ SECURE - Isolated network
spec:
  hostNetwork: false
```

**Unrestricted Communication**
```yaml
# ❌ BAD - No network policy
# All pods can communicate freely

# ✅ GOOD - Network policy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: app-policy
spec:
  podSelector:
    matchLabels:
      app: myapp
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: database
```

### 15. Image Scanning

**No Vulnerability Scanning**
```bash
# ❌ BAD - Images not scanned
docker push myapp:latest

# ✅ GOOD - Regular scanning
# Scan before pushing:
trivy image myapp:latest
# Or in CI:
- docker build -t myapp:latest .
- trivy image --exit-code 1 --severity HIGH,CRITICAL myapp:latest
- docker push myapp:latest
```

## Review Checklist

For each Dockerfile/container config, check:

- [ ] Using minimal, up-to-date base images
- [ ] Container runs as non-root user
- [ ] Minimal layers (combined RUN commands)
- [ ] No secrets or credentials in image
- [ ] Package installation with verification
- [ ] Build artifacts and caches cleaned up
- [ ] Proper file permissions (600 for secrets)
- [ ] Minimal image size (alpine, distroless preferred)
- [ ] COPY instead of ADD
- [ ] Health check configured
- [ ] Multi-stage builds for compiled applications
- [ ] Images signed and verified
- [ ] No privileged containers
- [ ] No hostPath volumes or justified
- [ ] Resource limits set (requests and limits)
- [ ] Network policies configured
- [ ] Regular vulnerability scanning

## Output Format

```markdown
## Container Security Review: [image_name/dockerfile]

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
