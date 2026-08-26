I am building a small REST API for managing a personal todo list.

- Problem: I keep my todos in scattered notes and lose track of what is due; I
  want one self-hosted place to track them, and I got fed up enough with the
  scattered notes to finally build it.
- Users: individual developers and small teams who want a simple self-hosted
  todo backend and do not want another SaaS account.
- Features: create, read, update, delete a todo; filter by completed status.
  A todo has a title, optional description, priority (high/medium/low) and a
  completed flag.
- Stack: FastAPI, SQLite via SQLAlchemy, pytest for tests.
- Success: all CRUD and filter endpoints work and are covered by passing tests.
- Out of scope for the MVP: auth, multi-user accounts, sharing, reminders, web UI.
- Constraints: single uvicorn process on a laptop or small VPS; list of 1000
  todos returns in under 200ms; one JSON error shape for every failure.
- Timeline: first milestone is create + list working end to end with tests.
