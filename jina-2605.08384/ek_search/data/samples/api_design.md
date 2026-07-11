# API Design Guide

## REST Conventions

All APIs follow REST conventions and return JSON.

### URL structure
- Collections: `GET /v1/users`
- Single resource: `GET /v1/users/{id}`
- Sub-resources: `GET /v1/users/{id}/orders`
- Actions (not REST-able): `POST /v1/users/{id}/activate`

### HTTP status codes
- `200 OK`: Success
- `201 Created`: Resource created (include Location header)
- `204 No Content`: Success with no body (DELETE)
- `400 Bad Request`: Invalid input
- `401 Unauthorized`: Missing or invalid auth token
- `403 Forbidden`: Valid token but insufficient permissions
- `404 Not Found`: Resource doesn't exist
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server bug

### Pagination
All list endpoints use cursor-based pagination:
```json
{
  "data": [...],
  "meta": {
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true,
    "total": 1542
  }
}
```

### Error format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email is required",
    "field": "email",
    "request_id": "req_abc123"
  }
}
```

## Authentication

All API requests require a Bearer token in the Authorization header:
```
Authorization: Bearer <token>
```

Tokens are obtained via `POST /v1/auth/token` with API key credentials.

## Versioning

APIs are versioned via URL path (`/v1/`, `/v2/`). Breaking changes require a new version. Old versions are deprecated with 6 months notice via deprecation headers.

## Rate Limiting

Default limits:
- 1000 requests/minute per API key
- 100 requests/second burst
- Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
