# Quick Start: Server Start Command

**Feature**: 010-server-start-command
**Audience**: CodeFRAME users (new and existing)
**Time to Complete**: 2 minutes

---

## Goal

Start the CodeFRAME dashboard web server and access the UI in your browser.

---

## Prerequisites

- CodeFRAME installed: `pip install codeframe` or cloned from GitHub
- Python 3.11+
- Terminal/command line access

---

## Step 1: Start the Server (Basic)

Open your terminal and run:

```bash
codeframe serve
```

You should see:

```
🌐 Starting dashboard server...
   URL: http://localhost:8080
   Press Ctrl+C to stop

INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

Your browser will automatically open to `http://localhost:8080` showing the CodeFRAME dashboard.

✅ **Success!** Your server is running.

---

## Step 2: Stop the Server

When you're done, press **Ctrl+C** in the terminal:

```bash
^C
✓ Server stopped
```

The server shuts down gracefully.

---

## Common Scenarios

### Scenario 1: Port 8080 Already In Use

**Problem**: Another service is using port 8080.

**Solution**: Use a different port with `--port`:

```bash
codeframe serve --port 3000
```

Your dashboard will be at `http://localhost:3000`.

---

### Scenario 2: Don't Auto-Open Browser

**Problem**: You don't want the browser to open automatically.

**Solution**: Use `--no-browser` flag:

```bash
codeframe serve --no-browser
```

Manually open `http://localhost:8080` in your browser when ready.

---

### Scenario 3: Development Mode (Auto-Reload)

**Problem**: You're modifying backend code and want changes to apply automatically.

**Solution**: Use `--reload` flag:

```bash
codeframe serve --reload
```

The server will restart automatically when you edit Python files.

**Note**: This is for development only. Do not use `--reload` in production.

---

### Scenario 4: Localhost Only (Not Accessible from Network)

**Problem**: You want the server to ONLY be accessible from your machine, not from the network.

**Solution**: Bind to `127.0.0.1` instead of `0.0.0.0`:

```bash
codeframe serve --host 127.0.0.1
```

This prevents other machines on your network from accessing the dashboard.

---

## All Options Reference

```bash
codeframe serve [OPTIONS]

Options:
  -p, --port INTEGER            Port to run server on [default: 8080]
  --host TEXT                   Host to bind to [default: 0.0.0.0]
  --open-browser/--no-browser   Auto-open browser [default: open-browser]
  --reload                      Enable auto-reload (development) [default: False]
  --help                        Show this message and exit
```

---

## Examples

### Example 1: Basic Usage (Default Settings)

```bash
codeframe serve
```

- Port: 8080
- Host: 0.0.0.0 (accessible from network)
- Browser: Opens automatically
- Reload: Disabled

---

### Example 2: Custom Port, No Browser

```bash
codeframe serve --port 5000 --no-browser
```

- Port: 5000
- Host: 0.0.0.0
- Browser: Does NOT open
- Reload: Disabled

Manually visit: `http://localhost:5000`

---

### Example 3: Development Mode

```bash
codeframe serve --port 8080 --reload
```

- Port: 8080
- Host: 0.0.0.0
- Browser: Opens automatically
- Reload: Enabled (restarts on code changes)

---

### Example 4: Secure Localhost-Only

```bash
codeframe serve --host 127.0.0.1 --port 8080
```

- Port: 8080
- Host: 127.0.0.1 (localhost only, not accessible from network)
- Browser: Opens automatically
- Reload: Disabled

---

## Troubleshooting

### Error: "Port 8080 is already in use"

**Cause**: Another process is using port 8080.

**Solutions**:
1. Find and stop the other process:
   ```bash
   # macOS/Linux
   lsof -i :8080
   kill <PID>

   # Windows
   netstat -ano | findstr :8080
   taskkill /PID <PID> /F
   ```

2. Use a different port:
   ```bash
   codeframe serve --port 8081
   ```

---

### Error: "uvicorn not found"

**Cause**: uvicorn is not installed.

**Solution**: Install uvicorn:

```bash
pip install uvicorn
```

Or reinstall CodeFRAME with all dependencies:

```bash
pip install -e ".[dev]"
```

---

### Error: "Module 'codeframe.ui.server' not found"

**Cause**: CodeFRAME is not properly installed or you're in the wrong directory.

**Solution**:

1. Install CodeFRAME:
   ```bash
   pip install -e .
   ```

2. Verify installation:
   ```bash
   python -c "import codeframe.ui.server"
   ```

---

### Warning: "Could not open browser"

**Cause**: Running in a headless environment (no GUI) or browser not found.

**Effect**: Server still runs fine, just doesn't open browser.

**Solution**: Manually open `http://localhost:8080` in your browser.

---

### Server Starts But Can't Access Dashboard

**Symptoms**: Server logs show "Uvicorn running" but browser shows "Connection refused".

**Cause**: Firewall blocking port or wrong host binding.

**Solutions**:

1. Check if port is actually listening:
   ```bash
   # macOS/Linux
   lsof -i :8080

   # Windows
   netstat -ano | findstr :8080
   ```

2. Try localhost explicitly:
   ```bash
   codeframe serve --host 127.0.0.1
   ```

3. Check firewall settings to allow port 8080.

---

## Next Steps

Now that your server is running:

1. **Create a Project**: Visit `http://localhost:8080` and fill out the project creation form
2. **Submit a PRD**: Describe your project's requirements to start discovery
3. **Answer Questions**: The Lead Agent will ask clarifying questions
4. **Watch Agents Work**: Monitor progress in real-time via the dashboard

See the main README.md for full workflow documentation.

---

## Integration with Other Commands

### Workflow: Init → Serve → Work

```bash
# 1. Initialize a new project
codeframe init my-app

# 2. Start the dashboard server
codeframe serve

# 3. (In browser) Create project, submit PRD, answer questions

# 4. (Optional) In another terminal, monitor status
codeframe status my-app
```

---

## FAQ

**Q: Can I run multiple servers on different ports?**
A: Yes! Each port runs independently:
```bash
# Terminal 1
codeframe serve --port 8080

# Terminal 2
codeframe serve --port 9000
```

**Q: How do I make the server accessible from another machine?**
A: Use `--host 0.0.0.0` (default) and make sure firewall allows the port. Then access via `http://<your-ip>:8080`.

**Q: Is there a background/daemon mode?**
A: Not currently. The server runs in the foreground so you can easily stop it with Ctrl+C. For production deployment, use a process manager like systemd, supervisor, or Docker.

**Q: Can I use HTTPS?**
A: Not directly with `serve` command. For HTTPS, use a reverse proxy (nginx, Caddy) in front of the server.

**Q: Does `--reload` work for frontend changes?**
A: No, `--reload` only restarts the Python backend. Frontend changes are handled by Next.js dev server (`npm run dev` in `web-ui/`).

---

## Command Cheat Sheet

| Scenario | Command |
|----------|---------|
| Basic start | `codeframe serve` |
| Custom port | `codeframe serve --port 3000` |
| No browser | `codeframe serve --no-browser` |
| Development | `codeframe serve --reload` |
| Localhost only | `codeframe serve --host 127.0.0.1` |
| Stop server | `Ctrl+C` |

---

## Video Walkthrough

*(To be added: 2-minute screencast showing serve command usage)*

---

## Related Documentation

- **README.md**: Main project documentation
- **Feature Spec**: `/home/frankbria/projects/codeframe/specs/010-server-start-command/spec.md`
- **Implementation Plan**: `/home/frankbria/projects/codeframe/specs/010-server-start-command/plan.md`
