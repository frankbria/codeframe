# Deployment Security Guide

## Overview

CodeFRAME agents execute code from user projects, including test commands, build scripts, and custom configurations. **Production deployments MUST implement proper isolation controls.**

## Security Model

### Threat Model

CodeFRAME's security model depends on the deployment environment:

| Deployment Type | Primary Security Control | Secondary Controls |
|----------------|-------------------------|-------------------|
| **SaaS (Multi-tenant)** | Container isolation | Command validation, sandboxing |
| **Self-hosted (Single user)** | User trust in projects | Optional security policies |
| **Local Development** | User responsibility | N/A |

### Defense in Depth Layers

1. **Infrastructure (PRIMARY)**: Container/VM isolation
2. **Application (SECONDARY)**: Command injection prevention, input validation
3. **Configuration (TERTIARY)**: User-defined security policies

## Production SaaS Deployment

### Required Security Controls

#### 1. Container Isolation (CRITICAL)

Use containerization with security profiles:

```yaml
# docker-compose.yml (example)
services:
  codeframe-worker:
    image: codeframe-agent:latest
    security_opt:
      - no-new-privileges:true
      - seccomp=default.json
      - apparmor=docker-default
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # Only if needed
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=1g
      - /var/run:rw,noexec,nosuid,size=100m
    user: "1000:1000"  # Non-root user
    pids_limit: 100
    mem_limit: 2g
    cpus: 1.0
```

#### 2. Network Isolation

Restrict network access for agent containers:

```yaml
# Option 1: No network access (most secure)
services:
  codeframe-worker:
    network_mode: none

# Option 2: Restricted network with allowlist
services:
  codeframe-worker:
    networks:
      - isolated
    dns:
      - 10.0.0.1  # Internal DNS only

networks:
  isolated:
    driver: bridge
    internal: true  # No external access
```

#### 3. Filesystem Isolation

- **Read-only root filesystem**: Prevents persistence of malicious changes
- **Temporary directories**: Use tmpfs for /tmp with noexec
- **Volume mounts**: Read-only mounts for code, read-write for output only

```yaml
volumes:
  - ./project:/workspace:ro  # Read-only project code
  - ./output:/output:rw      # Write-only output directory
```

#### 4. Resource Limits

Prevent resource exhaustion attacks:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 2G
      pids: 100
    reservations:
      cpus: '0.25'
      memory: 512M

ulimits:
  nproc: 100
  nofile: 1024
  fsize: 1073741824  # 1GB max file size
```

#### 5. Secrets Management

Never pass secrets as environment variables to agent containers:

```yaml
# ❌ BAD - Secrets exposed to agent
environment:
  - DATABASE_PASSWORD=secret123
  - API_KEY=key123

# ✅ GOOD - Secrets in separate service
services:
  codeframe-api:
    environment:
      - DATABASE_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password

  codeframe-worker:
    # No secrets - cannot access databases or external APIs
    environment:
      - WORKSPACE=/workspace
```

### Deployment Architecture

```
┌─────────────────────────────────────────────┐
│ Load Balancer / API Gateway                 │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│ CodeFRAME API Server (Stateless)            │
│ - Authentication                            │
│ - Project management                        │
│ - Queue management                          │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│ Message Queue (Redis/RabbitMQ)              │
└─────────────────┬───────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼──────┐    ┌───────▼──────┐
│ Worker Pod 1 │    │ Worker Pod N │
│ (Isolated)   │    │ (Isolated)   │
│              │    │              │
│ ┌──────────┐ │    │ ┌──────────┐ │
│ │Container │ │    │ │Container │ │
│ │per Agent │ │    │ │per Agent │ │
│ └──────────┘ │    │ └──────────┘ │
└──────────────┘    └──────────────┘
```

### Security Checklist

Before deploying to production:

- [ ] Containers run as non-root user
- [ ] Read-only root filesystem enabled
- [ ] Network isolation configured (no internet or allowlist only)
- [ ] Resource limits set (CPU, memory, processes, file size)
- [ ] Security profiles applied (AppArmor/SELinux/seccomp)
- [ ] Secrets not passed to worker containers
- [ ] Logging and monitoring configured
- [ ] Regular security audits scheduled
- [ ] Incident response plan documented

## Self-Hosted Deployment

### Security Considerations

For self-hosted deployments (single organization):

1. **Trust Boundary**: Users execute CodeFRAME on their own infrastructure
2. **Risk Model**: Similar to running `npm install` or `pip install` - arbitrary code execution
3. **Security Policy**: "Buyer beware" - only run on trusted projects

### Recommended Controls

Even for self-hosted deployments, consider:

- Dedicated user account for CodeFRAME (not root)
- Filesystem quotas and backups
- Network monitoring and logging
- Regular security updates

### Configuration

```python
# config/security.yml
deployment:
  mode: selfhosted
  security_policy:
    command_validation: warn  # warn, enforce, disabled
    allow_shell_operators: true
    safe_commands_only: false
```

## Local Development

For local development:

- CodeFRAME runs with your user permissions
- All security controls are advisory (warnings only)
- Only run on projects you trust
- Review test commands in configuration files before running

## Application Security Controls

### Command Injection Prevention

CodeFRAME implements defense-in-depth command execution security:

```python
# Automatic safe command detection
SAFE_COMMANDS = {"pytest", "npm", "cargo", "go", ...}

# Commands parsed safely
"pytest tests/" → shell=False (secure)
"npm run test" → shell=False (secure)

# Shell operators detected with warnings
"npm run build && npm test" → shell=True + WARNING log
```

**Behavior**: Warnings only, nothing blocked. All configurations work.

### Security Logging

Security events are logged at appropriate levels:

- **DEBUG**: Safe command execution (normal operation)
- **INFO**: Unknown command (consider adding to safe list)
- **WARNING**: Shell operators detected (potential security risk)
- **ERROR**: Command execution failures

### Future: User-Configured Security Policies

Planned for future releases:

```yaml
# .codeframe/security-policy.yml
security:
  enforcement_level: warn  # warn, strict, disabled

  allowed_commands:
    - pytest
    - npm
    - custom-test-runner

  allowed_shell_operators:
    - "&&"  # Allow build && test workflows

  blocked_patterns:
    - "rm -rf"
    - "curl http://"
    - "wget"

  require_approval:
    - "*://external-domain.com/*"
```

## Kubernetes Deployment

### Pod Security Policy Example

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: codeframe-worker
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault

  containers:
  - name: worker
    image: codeframe-agent:latest
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
    resources:
      limits:
        cpu: "1000m"
        memory: "2Gi"
        ephemeral-storage: "10Gi"
      requests:
        cpu: "100m"
        memory: "256Mi"
    volumeMounts:
      - name: tmp
        mountPath: /tmp
      - name: workspace
        mountPath: /workspace
        readOnly: true

  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 1Gi
    - name: workspace
      emptyDir: {}
```

### Network Policy Example

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: codeframe-worker-isolation
spec:
  podSelector:
    matchLabels:
      app: codeframe-worker
  policyTypes:
    - Ingress
    - Egress
  ingress: []  # No inbound traffic
  egress:
    - to:
      - podSelector:
          matchLabels:
            app: codeframe-api
      ports:
        - protocol: TCP
          port: 8080
    # Block all other egress (no internet)
```

## Monitoring and Auditing

### Security Metrics to Monitor

1. **Command Execution**:
   - Commands using shell=True (high risk)
   - Unknown commands executed
   - Failed command execution attempts

2. **Resource Usage**:
   - CPU/memory spikes (potential cryptomining)
   - Disk usage (potential data exfiltration)
   - Network connections (should be minimal/none)

3. **Container Events**:
   - Container restarts (potential crash attacks)
   - Failed security checks
   - Privileged escalation attempts

### Logging Best Practices

```python
# Security event logging
logger.warning(
    "shell_operator_detected",
    extra={
        "command": command,
        "project_id": project_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow(),
        "security_event": True,
    }
)
```

## Incident Response

### If a Security Incident Occurs

1. **Immediate Actions**:
   - Isolate affected worker containers
   - Stop processing new jobs from affected project
   - Collect logs and artifacts

2. **Investigation**:
   - Review command execution logs
   - Check for data exfiltration attempts
   - Analyze resource usage patterns
   - Review project configuration files

3. **Remediation**:
   - Update security policies
   - Patch vulnerabilities
   - Notify affected users (if multi-tenant)
   - Document lessons learned

## References

- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Kubernetes Security](https://kubernetes.io/docs/concepts/security/)
- [OWASP Container Security](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)

## Support

For security questions or to report vulnerabilities, see [SECURITY.md](../SECURITY.md).
