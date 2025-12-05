# Architecture Documentation

This directory contains technical architecture documentation for CodeFRAME. These documents explain system design decisions, data model semantics, and patterns used throughout the codebase.

## Documents

| Document | Description |
|----------|-------------|
| [task-identifiers.md](task-identifiers.md) | Task identifier types (`id` vs `task_number`), dependency semantics, and the tolerant lookup pattern |

## Purpose

Architecture documentation differs from other documentation types in the project:

| Type | Location | Purpose |
|------|----------|---------|
| **Architecture Docs** | `docs/architecture/` | System design decisions, data model semantics, cross-cutting patterns |
| **Feature Specs** | `specs/{feature}/` | Implementation requirements for specific features |
| **Sprint Summaries** | `sprints/` | What was delivered when, sprint-level documentation |
| **API Contracts** | `docs/api/` | Endpoint specifications and request/response formats |
| **Process Docs** | `docs/process/` | Development workflows and team procedures |

## When to Add Architecture Documentation

Add a new architecture document when:

1. **New data model patterns**: Introducing identifiers, relationships, or schemas that span multiple components
2. **Cross-cutting concerns**: Patterns used in multiple places (caching, error handling, etc.)
3. **Design rationale**: Explaining *why* something is built a certain way, not just *how*
4. **Migration paths**: Documenting how to evolve from one approach to another
5. **Trade-off analysis**: Recording decisions where multiple valid approaches existed

## Document Template

When creating new architecture documentation, include:

```markdown
# [Topic Name]

Brief description of what this document covers.

## Overview
High-level summary with key concepts.

## [Core Concept 1]
Detailed explanation with code examples.

## [Core Concept 2]
...

## Trade-offs and Recommendations
Comparison table and guidance.

## Related Files
Table of relevant source files with line numbers.

## Changelog
- Date: Initial documentation or updates
```

## Contributing

Before adding a new architecture document:

1. Check if an existing document already covers the topic
2. Consider whether this belongs in a feature spec instead
3. Keep documents focused on a single architectural concern
4. Include code examples with file paths and line numbers
5. Add your document to this README's index table
