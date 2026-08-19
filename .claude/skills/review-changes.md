---
name: review-changes
description: Review code changes using available diff or PR context
---

# Review Changes

Review code changes for the DevOps monitoring tool project.

## Usage

Run `/review-changes` to review pending changes.

## Review Checklist

### Backend (Python)
- [ ] Type hints present and correct
- [ ] Docstrings for public functions/classes
- [ ] Error handling with try/except blocks
- [ ] Logging added for important operations
- [ ] Environment variables use `settings.XXX`
- [ ] No hardcoded secrets or credentials
- [ ] SQLAlchemy/DB sessions properly managed
- [ ] Async functions use `async`/`await` correctly
- [ ] Tests added for new functionality

### Frontend (TypeScript/React)
- [ ] TypeScript types defined/imported
- [ ] Components follow existing patterns
- [ ] Props properly typed
- [ ] Error handling for API calls
- [ ] Loading states for async operations
- [ ] No `any` types (use specific types)
- [ ] CSS follows design system
- [ ] Tests added for new hooks/utils

### Kubernetes/Docker
- [ ] ConfigMap for non-sensitive config
- [ ] Secret for sensitive data
- [ ] Resource limits/requests defined
- [ ] Health checks configured
- [ ] Image tags specified (not `latest`)
- [ ] Namespace references consistent

## Common Patterns

### Backend API Endpoints
```python
# Good pattern
@router.get("/api/v1/resource")
async def get_resource(
    request: Request,
    resource_id: str,
) -> ResourceResponse:
    """Get a resource by ID."""
    try:
        resource = await service.get(resource_id)
        return ResourceResponse(success=True, resource=resource)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Frontend API Calls
```typescript
// Good pattern
const { data, error } = await useSWR(`/api/v1/resource/${id}`, fetcher);

if (error) return <ErrorState error={error} />;
if (!data) return <LoadingState />;

return <ResourceDisplay resource={data} />;
```

## Pre-commit Review

Before committing, run:
```bash
# Backend
cd backend
black app/
ruff check app/ --fix
mypy app/
pytest

# Frontend
cd frontend
eslint . --fix
tsc -b
npm test
```

## Security Considerations

- Never commit API keys or secrets
- Validate user input
- Sanitize output (XSS prevention)
- Use parameterized queries (SQL injection prevention)
- Check permissions before operations
