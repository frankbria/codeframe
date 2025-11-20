# API Contracts: Discovery Answer UI Integration

**Feature**: 012-discovery-answer-ui
**Date**: 2025-11-19

---

## Overview

This directory contains formal API contract specifications for the Discovery Answer UI Integration feature.

---

## Files

### 1. `api.openapi.yaml`

**Format**: OpenAPI 3.1.0
**Purpose**: REST API specification for discovery answer submission endpoint

**Contents**:
- POST `/api/projects/{project_id}/discovery/answer`
  - Request schema: `DiscoveryAnswer`
  - Response schema: `DiscoveryAnswerResponse`
  - Error responses: 400, 404, 422, 500
- Complete examples for all request/response scenarios
- Validation rules for answer length (1-5000 chars)

**Tools**:
- Validator: [openapi-validator](https://github.com/IBM/openapi-validator-cli)
- Code Generation: [openapi-generator](https://openapi-generator.tech/)
- Documentation: [Redoc](https://redocly.com/) or [Swagger UI](https://swagger.io/tools/swagger-ui/)

**Usage**:
```bash
# Validate OpenAPI spec
npx @openapitools/openapi-generator-cli validate -i api.openapi.yaml

# Generate TypeScript client
npx @openapitools/openapi-generator-cli generate \
  -i api.openapi.yaml \
  -g typescript-fetch \
  -o ./generated/api-client

# View documentation
npx redoc-cli serve api.openapi.yaml
```

---

### 2. `websocket.yaml`

**Format**: AsyncAPI 2.6.0
**Purpose**: WebSocket event specifications for real-time discovery updates

**Contents**:
- `discovery_answer_submitted` - Answer submission confirmation
- `discovery_question_presented` - Next question presentation
- `discovery_progress_updated` - Progress percentage updates
- `discovery_completed` - Discovery phase completion

**Tools**:
- Validator: [asyncapi-cli](https://github.com/asyncapi/cli)
- Code Generation: [asyncapi-codegen](https://github.com/asyncapi/generator)
- Documentation: [asyncapi/html-template](https://github.com/asyncapi/html-template)

**Usage**:
```bash
# Validate AsyncAPI spec
npx asyncapi validate websocket.yaml

# Generate HTML documentation
npx asyncapi generate fromTemplate websocket.yaml @asyncapi/html-template \
  -o ./generated/websocket-docs

# Generate TypeScript types
npx asyncapi generate models typescript websocket.yaml \
  -o ./generated/websocket-types
```

---

## Contract Validation

### Pre-Commit Checks

Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: validate-openapi
      name: Validate OpenAPI specs
      entry: npx @openapitools/openapi-generator-cli validate
      language: system
      files: \.openapi\.yaml$

    - id: validate-asyncapi
      name: Validate AsyncAPI specs
      entry: npx asyncapi validate
      language: system
      files: websocket\.yaml$
```

### Manual Validation

```bash
# Validate all contracts
cd specs/012-discovery-answer-ui/contracts

# OpenAPI validation
npx @openapitools/openapi-generator-cli validate -i api.openapi.yaml

# AsyncAPI validation
npx asyncapi validate websocket.yaml
```

---

## Integration with Backend

### FastAPI OpenAPI Integration

FastAPI automatically generates OpenAPI specs from route decorators. Our `api.openapi.yaml` serves as:

1. **Design Document**: Specification-first approach
2. **Validation**: Ensure implementation matches spec
3. **Client Generation**: Generate TypeScript client for frontend
4. **Testing**: Generate test cases from examples

**Comparison**:
```bash
# Generate OpenAPI from running FastAPI server
curl http://localhost:8080/openapi.json > generated-spec.json

# Compare with our specification
npx openapi-diff api.openapi.yaml generated-spec.json
```

---

## Integration with Frontend

### TypeScript Client Generation

```bash
# Generate type-safe API client
npx @openapitools/openapi-generator-cli generate \
  -i contracts/api.openapi.yaml \
  -g typescript-fetch \
  -o web-ui/src/generated/api

# Use in frontend
import { DiscoveryApi } from '@/generated/api';

const api = new DiscoveryApi();
const response = await api.submitDiscoveryAnswer({
  projectId: 123,
  discoveryAnswer: { answer: "My answer text" }
});
```

### WebSocket Type Generation

```bash
# Generate TypeScript types from AsyncAPI
npx asyncapi generate models typescript websocket.yaml \
  -o web-ui/src/generated/websocket-types

# Use in frontend
import { DiscoveryAnswerSubmittedPayload } from '@/generated/websocket-types';

ws.onmessage = (event) => {
  const message: DiscoveryAnswerSubmittedPayload = JSON.parse(event.data);
  if (message.type === 'discovery_answer_submitted') {
    console.log('Progress:', message.progress.percentage);
  }
};
```

---

## Contract-Driven Development Workflow

1. **Design Phase**:
   - Write OpenAPI/AsyncAPI specs first
   - Review with team
   - Validate specs

2. **Implementation Phase**:
   - Generate types and clients from specs
   - Implement backend endpoints matching spec
   - Implement frontend using generated client
   - Run contract tests

3. **Verification Phase**:
   - Compare implementation against spec
   - Ensure all examples work
   - Validate error responses

4. **Documentation Phase**:
   - Generate API docs from specs
   - Host docs with Redoc/AsyncAPI HTML
   - Link from main README

---

## Testing with Contracts

### Contract Testing (Pact)

```typescript
// Frontend contract test
import { pactWith } from 'jest-pact';
import { DiscoveryApi } from '@/generated/api';

pactWith({ consumer: 'WebUI', provider: 'DiscoveryAPI' }, (interaction) => {
  interaction('submit discovery answer', () => {
    given('project 123 exists and is in discovery phase');
    uponReceiving('a valid answer submission');
    withRequest({
      method: 'POST',
      path: '/api/projects/123/discovery/answer',
      body: { answer: 'Valid answer text' }
    });
    willRespondWith({
      status: 200,
      body: {
        success: true,
        next_question: 'What tech stack?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0
      }
    });
  });

  it('submits answer successfully', async () => {
    const api = new DiscoveryApi();
    const response = await api.submitDiscoveryAnswer({ ... });
    expect(response.success).toBe(true);
  });
});
```

---

## Versioning

**Current Version**: 1.0.0

**Semantic Versioning**:
- **MAJOR**: Breaking changes to request/response schemas
- **MINOR**: New optional fields or endpoints
- **PATCH**: Documentation updates, examples, clarifications

**Changelog**:
- `1.0.0` (2025-11-19): Initial specification for discovery answer submission

---

## References

- [OpenAPI 3.1 Specification](https://spec.openapis.org/oas/v3.1.0)
- [AsyncAPI 2.6 Specification](https://www.asyncapi.com/docs/reference/specification/v2.6.0)
- [FastAPI OpenAPI Support](https://fastapi.tiangolo.com/advanced/extending-openapi/)
- [TypeScript Fetch Client Generator](https://openapi-generator.tech/docs/generators/typescript-fetch/)

---

**Contracts Complete** ✅
**Ready for Implementation**: Backend and frontend can proceed independently using these specifications
