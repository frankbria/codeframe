# Context Management Quickstart

**Feature**: 007-context-management
**Audience**: Developers implementing or using the Virtual Project context management system
**Est. Reading Time**: 10 minutes

## Overview

This guide provides a quick introduction to the Context Management system, including key concepts, basic usage patterns, and integration examples.

## Key Concepts

### Tiered Memory System

The Context Management system uses a three-tier architecture inspired by CPU caches:

- **HOT Tier** (importance_score >= 0.8): Always loaded, critical recent context
- **WARM Tier** (0.4 <= score < 0.8): On-demand loading, supporting context
- **COLD Tier** (score < 0.4): Archived, rarely accessed, stale content

**Analogy**: Think of this like your email inbox:
- **HOT** = Starred emails you check daily
- **WARM** = Recent emails you might need
- **COLD** = Old emails you archive but don't delete

### Importance Scoring

Items are automatically scored based on:
```
importance_score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost
```

**Components**:
- **Type Weight**: TASK (1.0) > CODE (0.8) > ERROR (0.7) > TEST (0.6) > PRD (0.5)
- **Age Decay**: Exponential decay over time (e^(-0.5 × days))
- **Access Boost**: Log-normalized access frequency (log(count + 1) / 10)

### Flash Save

When agent context approaches token limits (80% threshold):
1. Calculate importance scores for all items
2. Archive COLD tier items to checkpoint
3. Clear working context
4. Reload only HOT tier items
5. Continue agent execution with reduced context

**Result**: 30-50% token reduction, enabling longer autonomous sessions

## Installation

### Prerequisites

```bash
# Python 3.11+ with required packages
pip install fastapi aiosqlite tiktoken pydantic

# Frontend dependencies (for dashboard visualization)
cd web-ui && npm install
```

### Database Migration

```bash
# Apply migrations to add context_checkpoints table and indexes
python -m codeframe.persistence.migrations.apply
```

**Expected Output**:
```
Migration 004: Add context_checkpoints table... OK
Migration 005: Add indexes to context_items... OK
All migrations applied successfully.
```

## Basic Usage

### For Worker Agents

#### 1. Save Context Items

```python
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import ContextItemType

class MyWorkerAgent(WorkerAgent):
    async def execute_task(self, task_id: int):
        # Save task description to context
        await self.save_context_item(
            item_type=ContextItemType.TASK,
            content=f"Implement user authentication with JWT tokens"
        )

        # Save code snippet
        await self.save_context_item(
            item_type=ContextItemType.CODE,
            content="def authenticate_user(username, password): ..."
        )

        # Save error if something fails
        try:
            result = await self.do_work()
        except Exception as e:
            await self.save_context_item(
                item_type=ContextItemType.ERROR,
                content=f"Authentication failed: {str(e)}"
            )
```

#### 2. Load Context

```python
# Load only HOT tier (default)
hot_items = await self.load_context(tier='HOT')

# Load WARM tier on-demand
warm_items = await self.load_context(tier='WARM')

# Load all tiers (rare, for debugging)
all_items = await self.load_context(tier=None)
```

#### 3. Flash Save Before Token Limit

```python
# Check if flash save needed
if await self.should_flash_save():
    result = await self.flash_save()
    print(f"Flash save completed:")
    print(f"  - Archived {result.items_archived} COLD items")
    print(f"  - Retained {result.hot_items_retained} HOT items")
    print(f"  - Token reduction: {result.reduction_percentage:.1f}%")
```

### For API Consumers

#### Create Context Item

```bash
curl -X POST http://localhost:8000/api/agents/backend-worker-001/context \
  -H "Content-Type: application/json" \
  -d '{
    "item_type": "TASK",
    "content": "Implement user login endpoint"
  }'
```

**Response**:
```json
{
  "id": 123,
  "agent_id": "backend-worker-001",
  "item_type": "TASK",
  "content": "Implement user login endpoint",
  "importance_score": 0.95,
  "tier": "HOT",
  "access_count": 0,
  "created_at": "2025-11-14T11:30:00Z",
  "last_accessed": "2025-11-14T11:30:00Z"
}
```

#### Get Context Stats

```bash
curl http://localhost:8000/api/agents/backend-worker-001/context/stats
```

**Response**:
```json
{
  "agent_id": "backend-worker-001",
  "total_items": 150,
  "hot_count": 20,
  "warm_count": 85,
  "cold_count": 45,
  "total_tokens": 125000,
  "hot_tokens": 35000,
  "warm_tokens": 60000,
  "cold_tokens": 30000,
  "last_updated": "2025-11-14T11:30:00Z"
}
```

#### Trigger Flash Save

```bash
curl -X POST http://localhost:8000/api/agents/backend-worker-001/flash-save
```

**Response**:
```json
{
  "checkpoint_id": 45,
  "agent_id": "backend-worker-001",
  "items_count": 150,
  "items_archived": 45,
  "hot_items_retained": 20,
  "token_count_before": 125000,
  "token_count_after": 35000,
  "reduction_percentage": 72.0,
  "created_at": "2025-11-14T11:35:00Z"
}
```

## Integration Examples

### Example 1: Automatic Flash Save in Long-Running Task

```python
class BackendWorkerAgent(WorkerAgent):
    async def execute_long_task(self, task_id: int):
        """Execute multi-hour task with automatic flash saves."""

        # Save initial task context
        task = self.db.get_task(task_id)
        await self.save_context_item(
            item_type=ContextItemType.TASK,
            content=f"Task {task_id}: {task['description']}"
        )

        # Work loop with flash save checks
        for step in range(1, 100):
            # Do work
            result = await self.execute_step(step)

            # Save intermediate results
            await self.save_context_item(
                item_type=ContextItemType.CODE,
                content=f"Step {step} result: {result}"
            )

            # Check if flash save needed
            current_tokens = await self.count_context_tokens()
            if current_tokens >= self.FLASH_SAVE_THRESHOLD:
                logger.info(f"Step {step}: Triggering flash save (tokens: {current_tokens})")
                flash_result = await self.flash_save()
                logger.info(f"Flash save: {flash_result.reduction_percentage:.1f}% reduction")

        # Final tier update
        await self.update_tiers()
```

### Example 2: Dashboard Context Visualization

```typescript
// React component for displaying context stats
import React, { useEffect, useState } from 'react';
import { fetchContextStats } from '../api/context';

interface ContextPanelProps {
  agentId: string;
}

export const ContextPanel: React.FC<ContextPanelProps> = ({ agentId }) => {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const loadStats = async () => {
      const data = await fetchContextStats(agentId);
      setStats(data);
    };

    loadStats();
    const interval = setInterval(loadStats, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, [agentId]);

  if (!stats) return <div>Loading...</div>;

  return (
    <div className="context-panel">
      <h3>Context Memory: {stats.total_items} items</h3>

      <div className="tier-breakdown">
        <div className="tier hot">
          <span className="count">{stats.hot_count}</span>
          <span className="label">HOT</span>
          <span className="tokens">{(stats.hot_tokens / 1000).toFixed(1)}k tokens</span>
        </div>

        <div className="tier warm">
          <span className="count">{stats.warm_count}</span>
          <span className="label">WARM</span>
          <span className="tokens">{(stats.warm_tokens / 1000).toFixed(1)}k tokens</span>
        </div>

        <div className="tier cold">
          <span className="count">{stats.cold_count}</span>
          <span className="label">COLD</span>
          <span className="tokens">{(stats.cold_tokens / 1000).toFixed(1)}k tokens</span>
        </div>
      </div>

      <div className="total-usage">
        Total: {(stats.total_tokens / 1000).toFixed(1)}k / 180k tokens
        ({((stats.total_tokens / 180000) * 100).toFixed(1)}%)
      </div>
    </div>
  );
};
```

### Example 3: Periodic Tier Reassignment (Cron Job)

```python
import asyncio
from datetime import datetime
from codeframe.persistence.database import Database

async def reassign_tiers_for_all_agents():
    """Periodic task to recalculate importance scores and reassign tiers."""
    db = Database()

    # Get all active agents
    agents = db.get_all_agents()

    for agent in agents:
        agent_id = agent['agent_id']

        # Get all context items for this agent
        items = db.list_context_items(agent_id=agent_id, tier=None)

        updated_count = 0
        for item in items:
            # Recalculate importance score
            new_score = calculate_importance_score(
                item_type=item['item_type'],
                created_at=item['created_at'],
                access_count=item['access_count'],
                last_accessed=item['last_accessed']
            )

            # Assign new tier
            new_tier = assign_tier(new_score)

            # Update if changed
            if new_tier != item['tier']:
                db.update_context_item_tier(item['id'], new_tier, new_score)
                updated_count += 1

        if updated_count > 0:
            print(f"Agent {agent_id}: Updated {updated_count} items")

# Run every 5 minutes
if __name__ == "__main__":
    while True:
        asyncio.run(reassign_tiers_for_all_agents())
        time.sleep(300)  # 5 minutes
```

## Performance Tips

### 1. Batch Context Saves

**Bad** (N database writes):
```python
for error in errors:
    await self.save_context_item(ContextItemType.ERROR, str(error))
```

**Good** (1 batched write):
```python
error_batch = [str(e) for e in errors]
await self.save_context_items_batch(ContextItemType.ERROR, error_batch)
```

### 2. Cache Token Counts

```python
# Enable token count caching (saves 90% of tiktoken calls)
from codeframe.lib.token_counter import TokenCounter

counter = TokenCounter(cache_enabled=True)
token_count = counter.count_tokens(content)  # First call: calculates
token_count = counter.count_tokens(content)  # Second call: cached
```

### 3. Use Tier Filters

**Bad** (loads all items, filters in Python):
```python
all_items = await self.load_context(tier=None)
hot_items = [item for item in all_items if item.tier == 'HOT']
```

**Good** (database-level filtering):
```python
hot_items = await self.load_context(tier='HOT')
```

## Troubleshooting

### Problem: Flash save not triggering

**Symptoms**: Agent context grows to 180k tokens without flash save

**Solutions**:
1. Check `FLASH_SAVE_THRESHOLD` is set correctly (should be 0.80 or 144k tokens)
2. Verify token counting is working: `await self.count_context_tokens()`
3. Check logs for flash save trigger checks

### Problem: Too many items in HOT tier

**Symptoms**: Flash save doesn't reduce token count enough

**Solutions**:
1. Lower HOT tier threshold from 0.8 to 0.7
2. Increase age decay rate (higher λ value)
3. Review item type weights (may be too high)

### Problem: Context quality degraded after flash save

**Symptoms**: Agent "forgets" important context after flash save

**Solutions**:
1. Increase HOT tier threshold from 0.8 to 0.9
2. Boost access_count for critical items before flash save
3. Manually mark items as HOT: `db.update_context_item_tier(item_id, 'HOT', 1.0)`

## Next Steps

- **Read the spec**: [spec.md](spec.md) for complete feature requirements
- **Review the data model**: [data-model.md](data-model.md) for schema details
- **API reference**: [contracts/openapi.yaml](contracts/openapi.yaml)
- **Implementation plan**: [plan.md](plan.md) for development phases

## References

- **Research**: [research.md](research.md) - Importance scoring algorithms
- **Constitution**: Principle III (Context Efficiency)
- **Related Sprints**: Sprint 5 (Async Workers), Sprint 6 (Human in Loop)
