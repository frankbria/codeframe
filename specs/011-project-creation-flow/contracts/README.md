# API Contracts

This directory contains API specifications for the Project Creation Flow feature.

## Files

### `api.openapi.yaml`

OpenAPI 3.0 specification for the `POST /api/projects` endpoint.

**Covers**:
- Request body schema (name, description, projectType)
- Response schemas (success, error responses)
- Validation rules and constraints
- HTTP status codes (201, 400, 409, 422, 500)
- Example requests and responses

**Usage**:

1. **View in Swagger UI** (recommended):
   ```bash
   # Install swagger-ui-cli globally
   npm install -g swagger-ui-cli

   # Serve the spec
   swagger-ui-cli serve api.openapi.yaml

   # Open http://localhost:8080 in browser
   ```

2. **Validate spec**:
   ```bash
   # Install openapi-cli
   npm install -g @redocly/cli

   # Lint the spec
   openapi lint api.openapi.yaml
   ```

3. **Generate TypeScript types** (optional):
   ```bash
   # Install openapi-typescript
   npm install -D openapi-typescript

   # Generate types
   npx openapi-typescript api.openapi.yaml -o ../../../web-ui/src/types/generated/api.ts
   ```

## Validation Rules Summary

| Field | Type | Min Length | Max Length | Pattern | Required |
|-------|------|------------|------------|---------|----------|
| `name` | string | 3 | 100 | `/^[a-z0-9-_]+$/` | Yes |
| `description` | string | 10 | 500 | None | Yes |
| `projectType` | enum | N/A | N/A | `python\|typescript\|fullstack\|other` | No (default: `python`) |

## Status Codes

- **201 Created**: Project successfully created
- **400 Bad Request**: Invalid input format (e.g., name contains uppercase)
- **409 Conflict**: Duplicate project name
- **422 Unprocessable Entity**: Pydantic validation error (missing required field)
- **500 Internal Server Error**: Workspace creation failed

## Example Request

```bash
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-awesome-app",
    "description": "A full-stack application for managing team tasks",
    "projectType": "fullstack"
  }'
```

## Example Response (201 Created)

```json
{
  "id": 42,
  "name": "my-awesome-app",
  "status": "init",
  "phase": "discovery",
  "created_at": "2025-11-18T18:30:00Z"
}
```

## Example Error (409 Conflict)

```json
{
  "detail": "Project with name 'my-awesome-app' already exists"
}
```

---

**Last Updated**: 2025-11-18
**Feature**: 011-project-creation-flow
