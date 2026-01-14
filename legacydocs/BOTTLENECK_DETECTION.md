# Workflow Bottleneck Detection

## Overview

The `LeadAgent.detect_bottlenecks()` method identifies workflow inefficiencies in real-time autonomous agent execution. It detects four primary bottleneck types with automatic severity classification and actionable recommendations.

## Configuration

The detection system uses configurable thresholds defined as class attributes on `LeadAgent`:

```python
DEPENDENCY_WAIT_THRESHOLD_MINUTES = 60       # Minutes before flagging blocked tasks
AGENT_OVERLOAD_THRESHOLD = 5                 # Tasks per agent threshold
CRITICAL_PATH_THRESHOLD = 3                  # Dependent tasks to flag as critical
CRITICAL_SEVERITY_WAIT_MINUTES = 120         # Minutes = critical severity
HIGH_SEVERITY_WAIT_MINUTES = 60              # Minutes = high severity
```

## Bottleneck Types

### 1. Dependency Wait

Detects tasks stuck on blocked dependencies.

**Triggers:**
- Task status = "blocked" OR task in blocked_tasks mapping
- Wait time >= 60 minutes (configurable)

**Severity Levels:**
- Critical: >= 120 minutes
- High: >= 60 minutes
- Medium: < 60 minutes

**Example Output:**
```python
{
    "type": "dependency_wait",
    "task_id": 42,
    "wait_time_minutes": 95,
    "blocking_task_id": 37,
    "severity": "high",
    "recommendation": "Task 42 has been waiting 95min on task 37. Investigate or manually unblock dependency."
}
```

### 2. Agent Overload

Detects agents with excessive task assignments.

**Triggers:**
- Agent status = "busy" AND workload > AGENT_OVERLOAD_THRESHOLD (default: 5)
- **Current Architecture**: Workload is binary (0 if idle, 1 if busy), so this bottleneck won't trigger in practice
- **Future-Ready**: Detection logic supports task queues when agents can handle multiple concurrent tasks

**Severity Levels:**
- High: workload > 8
- Medium: workload > 5
- Low: workload <= 5

**Example Output:**
```python
{
    "type": "agent_overload",
    "agent_id": "worker-1",
    "assigned_tasks": 6,  # In future queue-based architecture
    "severity": "medium",
    "recommendation": "Agent worker-1 is overloaded with 6 tasks. Consider scaling up agents or re-distributing tasks."
}
```

### 3. Agent Idle

Detects idle agents while pending work exists.

**Triggers:**
- At least one agent with status = "idle"
- At least one task with status = "pending"

**Severity:** Always "medium"

**Example Output:**
```python
{
    "type": "agent_idle",
    "idle_agents": ["agent-1", "agent-2"],
    "severity": "medium",
    "recommendation": "Agents idle (agent-1, agent-2) while pending tasks exist. Check task assignment logic or dependencies."
}
```

### 4. Critical Path

Detects high-impact tasks blocking many dependents.

**Triggers:**
- Task status in ["pending", "assigned", "in_progress", "blocked"]
- Task has >= 3 dependent tasks (configurable)

**Severity Levels:**
- Critical: >= 5 dependents
- High: >= 3 dependents
- Medium: < 3 dependents

**Example Output:**
```python
{
    "type": "critical_path",
    "task_id": 15,
    "blocked_dependents": 7,
    "severity": "critical",
    "recommendation": "Task 15 blocks 7 dependent tasks. Prioritize this task or parallelize blocking dependencies."
}
```

## API Usage

### Basic Detection

```python
from codeframe.agents.lead_agent import LeadAgent

lead_agent = LeadAgent(
    project_id=1,
    db=db,
    api_key="anthropic-key"
)

# Run bottleneck detection
bottlenecks = lead_agent.detect_bottlenecks()

for bottleneck in bottlenecks:
    print(f"[{bottleneck['severity'].upper()}] {bottleneck['type']}")
    print(f"  {bottleneck['recommendation']}")
```

### Filtering by Severity

```python
bottlenecks = lead_agent.detect_bottlenecks()

# Get only critical/high severity
important = [b for b in bottlenecks if b['severity'] in ['critical', 'high']]

# Focus on critical items
for bn in important:
    logger.warning(f"URGENT: {bn['recommendation']}")
```

### Monitoring Agent Workload

```python
bottlenecks = lead_agent.detect_bottlenecks()

# Find overloaded agents
overloaded = [b for b in bottlenecks if b['type'] == 'agent_overload']

for bn in overloaded:
    agent_id = bn['agent_id']
    task_count = bn['assigned_tasks']
    print(f"Agent {agent_id} has {task_count} tasks")
```

### Identifying Stuck Tasks

```python
bottlenecks = lead_agent.detect_bottlenecks()

# Find tasks waiting on dependencies
stuck = [b for b in bottlenecks if b['type'] == 'dependency_wait']

for bn in stuck:
    wait_time = bn['wait_time_minutes']
    task_id = bn['task_id']
    blocker_id = bn['blocking_task_id']
    print(f"Task {task_id} stuck for {wait_time}min on task {blocker_id}")
```

## Performance Characteristics

- **Detection time:** ~100-500ms (varies with task/agent count)
- **Memory:** O(n) where n = total tasks + agents
- **Database calls:** 3 (get_project_tasks, get_agent_status, dependency graph)
- **Typical bottleneck count:** 0-5 per detection run

## Integration with Monitoring

### Periodic Detection

```python
import asyncio

async def monitor_bottlenecks(lead_agent, interval_seconds=30):
    """Continuously monitor for bottlenecks."""
    while True:
        bottlenecks = lead_agent.detect_bottlenecks()

        # Alert on critical issues
        critical = [b for b in bottlenecks if b['severity'] == 'critical']
        if critical:
            print(f"CRITICAL: {len(critical)} workflow issues detected")
            for bn in critical:
                print(f"  - {bn['recommendation']}")

        await asyncio.sleep(interval_seconds)

# Run monitoring task
asyncio.create_task(monitor_bottlenecks(lead_agent))
```

### Webhook Notifications

```python
def detect_and_notify(lead_agent, webhook_url):
    """Detect bottlenecks and send notifications."""
    bottlenecks = lead_agent.detect_bottlenecks()

    for bn in bottlenecks:
        if bn['severity'] == 'critical':
            requests.post(webhook_url, json={
                'type': 'bottleneck_detected',
                'bottleneck_type': bn['type'],
                'severity': bn['severity'],
                'recommendation': bn['recommendation'],
                'timestamp': datetime.now().isoformat()
            })
```

## Testing

The implementation includes 38 comprehensive tests covering:

- Wait time calculation (valid/invalid timestamps, edge cases)
- Agent workload computation
- Blocking relationships retrieval
- Severity determination (all bottleneck types)
- Recommendation generation (all bottleneck types)
- Full detection workflow (single/multiple bottlenecks)
- Exception handling and error recovery
- Threshold-based filtering

Run tests with:

```bash
uv run pytest tests/agents/test_bottleneck_detection.py -xvs
```

## Best Practices

1. **Run detection periodically:** Execute every 30-60 seconds during active execution
2. **Act on critical items:** Resolve critical/high severity bottlenecks immediately
3. **Monitor trends:** Track bottleneck frequency to identify systemic issues
4. **Adjust thresholds:** Tune detection parameters based on your workload patterns
5. **Log findings:** Record all detected bottlenecks for post-mortem analysis

## Troubleshooting

### No bottlenecks detected (but tasks seem stuck)

- Verify task timestamps are valid ISO format
- Check agent pool is properly initialized
- Ensure dependency resolver has built the dependency graph
- Confirm database queries return expected data

### False positives on agent_idle

- Verify pending tasks actually have unmet dependencies
- Check task status values are correct ("pending", not "PENDING", etc.)
- Review agent idle timeout logic

### Performance degradation during detection

- Large task counts (>1000) may increase detection time
- Consider running detection asynchronously in background
- Cache agent_status results if called frequently

## File Locations

- **Implementation:** `/home/frankbria/projects/codeframe/codeframe/agents/lead_agent.py` (lines 684-942)
- **Tests:** `/home/frankbria/projects/codeframe/tests/agents/test_bottleneck_detection.py` (38 tests, 100% passing)
- **Configuration:** `LeadAgent` class attributes (lines 38-43)

## Version History

- **v1.0.0** (2025-12-17): Initial implementation with 4 bottleneck types, full test coverage
