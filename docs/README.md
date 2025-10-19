# CodeFRAME Documentation

This directory contains archived and reference documentation for the CodeFRAME project.

## Directory Structure

### `/archive/sprint1/`
Historical implementation results from Sprint 1 (Week 1):
- `CF8.4_RESULTS.md` - cf-8.4 task implementation results
- `SPRINT1_COMPLETE.md` - Sprint 1 completion report
- `TDD_CF8_RESULTS.md` - TDD implementation: Database CRUD (cf-8.1)
- `TDD_CF8.2_RESULTS.md` - TDD implementation: Server database init (cf-8.2)
- `TDD_CF8.3_RESULTS.md` - TDD implementation: Wire endpoints (cf-8.3)
- `TDD_CF9_RESULTS.md` - TDD implementation: Anthropic provider & Lead Agent (cf-9)
- `TDD_CF10_RESULTS.md` - TDD implementation: Agent lifecycle (cf-10)

### `/archive/sprint3/`
Production bug fixes and WebSocket analysis from Sprint 3:
- `cf-46-production-bugs-sprint3-staging.md` - Production bugs blocking Sprint 3 staging demo
- `cf-46-websocket-root-cause-analysis.md` - Comprehensive WebSocket connectivity root cause analysis
- `cf-46-bug2-websocket-solution-summary.md` - WebSocket bug fix solution summary

### `/issues/`
Active issue tracking and analysis:
- `cf-47-dashboard-gaps.md` - Dashboard gaps and enhancement tracking

### `/process/`
Development process and setup documentation:
- `TDD_WORKFLOW.md` - Test-Driven Development workflow guide
- `WEB_UI_SETUP.md` - Web UI setup and configuration guide

### Root-Level Active Docs
Current active documentation maintained in `/docs/`:
- `API_CONTRACT_ROADMAP.md` - API contract design and roadmap
- `BIG_PICTURE.md` - High-level architecture and vision
- `CF-41_BACKEND_WORKER_AGENT_DESIGN.md` - Backend worker agent design (cf-41)
- `CLAUDE.md` - Claude-specific development notes and guidelines
- `REMOTE_STAGING_DEPLOYMENT.md` - Remote staging deployment guide
- `SPRINT2_PLAN.md` - Sprint 2 planning documentation
- `STAGING_SERVER.md` - Staging server configuration and setup
- `nginx-websocket-config.md` - Nginx WebSocket configuration guide
- `self_correction_workflow.md` - Self-correction workflow documentation

## Current Active Documentation

Active documentation is kept in the project root directory:
- `README.md` - Project overview and quick start
- `CODEFRAME_SPEC.md` - Complete technical specification
- `AGILE_SPRINTS.md` - Sprint plan and progress tracking
- `TESTING.md` - Manual testing guide and checklist
- `CONTRIBUTING.md` - Contribution guidelines
- `CONCEPTS_INTEGRATION.md` - General concepts integration analysis

## Archive Policy

When a sprint is complete or issues are resolved:
1. Move all sprint-specific implementation results to `/archive/sprint{N}/`
2. Move resolved issue analysis to appropriate archive location
3. Keep only current, active documentation in `/docs/` and project root
4. Process documentation stays in `/process/` for ongoing reference
5. Update this README with new archive entries
6. Maintain clear separation between historical records and active docs
