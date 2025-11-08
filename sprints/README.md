# Codeframe Sprints

This directory contains sprint planning and completion documents for the Codeframe project.

## Sprint Status Overview

| Sprint | Name | Status | Files |
|--------|------|--------|-------|
| Sprint 0 | Foundation | ✅ Complete | Database, basic models |
| Sprint 1 | Hello Codeframe | ✅ Complete | CLI, basic project creation |
| Sprint 2 | Socratic Discovery | ✅ Complete | Discovery agent, PRD generation |
| Sprint 3 | Single Agent MVP | ✅ Complete | Backend worker, self-correction |
| Sprint 4 | Multi-Agent System | ✅ Complete | Lead agent, dependencies, parallel execution |
| Sprint 4.5 | Project Schema Refactor | ✅ Complete | Flexible source types, workspace management |
| Sprint 5 | Async Worker Agents | ✅ Complete | Async/await migration (cf-48) |
| **Sprint 6** | **Human in the Loop** | ⚠️ **Schema Only** | Blocker system (planned) |
| **Sprint 7** | **Context Management** | ⚠️ **Schema Only** | Context tiers, flash save (planned) |
| **Sprint 8** | **Agent Maturity** | ⚠️ **Schema Only** | Learning, adaptive instructions (planned) |
| **Sprint 9** | **Review & Polish** | 📋 **Planned** | Review agent, quality gates (planned) |

## File Naming Convention

- `sprint-NN-name.md` - Sprint planning/completion document
- Completed sprints have detailed implementation notes
- Planned sprints have status indicators and current state assessment

## Sprint Document Structure

Each sprint file contains:
- Status badge (✅ Complete, ⚠️ Schema Only, 📋 Planned)
- Goal and user story
- Task breakdown (P0 core, P1 enhancements)
- Definition of Done
- Current status (what exists vs. what's missing)
- Implementation notes and blockers
- References to related specs and dependencies

## Audit Findings

Sprints 6-9 were audited on 2025-11-08. Key findings:
- **Schema exists** for all planned features (blockers, context_items, checkpoints)
- **No implementation code** for Sprint 6-9 features
- **Issue ID conflicts**: cf-26 through cf-44 reused from earlier sprints
- **Action required**: Create new non-conflicting issue IDs before starting work

See `/home/frankbria/projects/codeframe/AUDIT_SUMMARY.md` for full details.

## Next Steps

1. Review planned sprint files (sprint-06 through sprint-09)
2. Create new beads issues with non-conflicting IDs
3. Prioritize Sprint 6 (Human in the Loop) as next major feature
4. Validate database schema matches implementation needs
5. Begin implementation with working demos as Definition of Done

## References

- **AGILE_SPRINTS.md** - Full sprint descriptions with functional demos
- **AUDIT_SUMMARY.md** - Accuracy audit of sprint completion status
- **specs/** - Detailed feature specifications
- **.beads/** - Issue tracking database
