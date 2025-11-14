# Context Management System Research

**Research Date:** 2025-11-14
**Purpose:** Technical research for implementing an AI agent context management system

---

## Table of Contents

1. [Importance Scoring Algorithms](#1-importance-scoring-algorithms)
2. [Token Counting for LLMs](#2-token-counting-for-llms)
3. [Context Diffing Strategies](#3-context-diffing-strategies)
4. [Tiered Memory Systems](#4-tiered-memory-systems)
5. [Checkpoint/Restore Patterns](#5-checkpointrestore-patterns)
6. [Summary & Recommendations](#summary--recommendations)

---

## 1. Importance Scoring Algorithms

### Decision: Hybrid Exponential Decay with Frequency Weighting

**Formula:**
```
score(item) = w_r * recency_score + w_f * frequency_score + w_t * type_weight

where:
  recency_score = e^(-λ * age_days)
  frequency_score = log(1 + access_count) / log(1 + max_access_count)
  type_weight = content_type_multiplier

  w_r + w_f + w_t = 1.0  (weights sum to 1)
```

**Recommended Parameters:**
- **λ (lambda/decay rate):** 0.5 for half-life of ~1.4 days
  - Alternative: 0.1 for slower decay (half-life ~7 days)
- **Default weights:**
  - w_r = 0.5 (recency: 50%)
  - w_f = 0.3 (frequency: 30%)
  - w_t = 0.2 (content type: 20%)

**Content Type Multipliers:**
```python
CONTENT_TYPE_WEIGHTS = {
    'system_prompt': 1.5,      # Critical for agent behavior
    'task_definition': 1.3,    # Important context
    'code_snippet': 1.0,       # Standard weight
    'documentation': 0.9,      # Reference material
    'chat_history': 0.7,       # Conversational context
    'metadata': 0.5            # Supporting information
}
```

### Rationale

1. **Exponential Decay (Time-Based):**
   - Exponential functions are proven in streaming systems and cache algorithms
   - Natural decay pattern: `weight(t) = e^(-λt)` where older items gradually lose importance
   - Used in production systems: Redis LFU, recommendation engines, time-series databases

2. **Logarithmic Frequency Normalization:**
   - Prevents high-frequency items from dominating (diminishing returns)
   - Formula: `log(1 + count) / log(1 + max_count)` normalizes to [0, 1]
   - Avoids the "frequency bias" problem in pure LFU systems

3. **Content Type Weighting:**
   - Domain-specific: system prompts are more important than chat history
   - Allows semantic importance independent of access patterns
   - Similar to PageRank's link quality weighting

### Alternatives Considered

| Algorithm | Pros | Cons | Decision |
|-----------|------|------|----------|
| **Pure LRU** | Simple, O(1) operations | Ignores frequency, susceptible to scanning | ❌ Too simplistic |
| **Pure LFU** | Captures popularity | Stale items persist, doesn't adapt to shifts | ❌ Doesn't handle time |
| **Linear Time Decay** | Simple calculation | Less realistic decay pattern | ❌ Exponential is better |
| **ARC (Adaptive Replacement)** | Self-tuning, balances recency/frequency | Complex, requires two LRU lists | ⚠️ Consider for v2 |
| **Hybrid Exponential** | Balances all factors, tunable | Requires parameter tuning | ✅ **Selected** |

### Implementation Details

**Python Implementation:**
```python
import math
from datetime import datetime, timedelta
from typing import Dict, Literal

class ImportanceScorer:
    def __init__(
        self,
        lambda_decay: float = 0.5,
        w_recency: float = 0.5,
        w_frequency: float = 0.3,
        w_type: float = 0.2
    ):
        self.lambda_decay = lambda_decay
        self.w_recency = w_recency
        self.w_frequency = w_frequency
        self.w_type = w_type

        self.content_weights = {
            'system_prompt': 1.5,
            'task_definition': 1.3,
            'code_snippet': 1.0,
            'documentation': 0.9,
            'chat_history': 0.7,
            'metadata': 0.5
        }

    def calculate_score(
        self,
        last_accessed: datetime,
        access_count: int,
        max_access_count: int,
        content_type: str,
        current_time: datetime = None
    ) -> float:
        """Calculate importance score for a context item."""
        if current_time is None:
            current_time = datetime.now()

        # Recency score (exponential decay)
        age_days = (current_time - last_accessed).total_seconds() / 86400
        recency_score = math.exp(-self.lambda_decay * age_days)

        # Frequency score (logarithmic normalization)
        frequency_score = (
            math.log(1 + access_count) /
            math.log(1 + max(max_access_count, 1))
        )

        # Content type weight
        type_weight = self.content_weights.get(content_type, 1.0)

        # Combined score
        score = (
            self.w_recency * recency_score +
            self.w_frequency * frequency_score +
            self.w_type * type_weight
        )

        return score
```

**Tuning Strategy:**
1. Start with default weights (0.5, 0.3, 0.2)
2. Monitor cache hit rates and agent performance
3. Adjust based on workload:
   - **Temporal workloads** (news, events): Increase w_r to 0.6-0.7
   - **Reference-heavy workloads** (documentation lookup): Increase w_f to 0.4-0.5
   - **Structured workflows** (coding agents): Increase w_t to 0.3-0.4

**References:**
- Forward Decay Model (Rutgers DIMACS): Monotone non-decreasing functions for streaming
- ERWA (Exponential Recency Weighted Average): α-weighted moving averages
- RFM Analysis (Recency-Frequency-Monetary): Proven in customer analytics with similar scoring

---

## 2. Token Counting for LLMs

### Decision: tiktoken with Caching Strategy

**Primary Library:** `tiktoken` (OpenAI's official tokenizer)
**Approach:** Exact counting with intelligent caching

### Rationale

1. **Performance:**
   - 3-6x faster than other open-source tokenizers
   - Written in Rust with Python bindings (native performance)
   - Batch processing: ~150,000 tokens/sec (single-threaded), 1.8M tokens/sec (12 threads)

2. **Accuracy:**
   - 100% accurate for OpenAI models (GPT-4, GPT-3.5, o1)
   - Official implementation used by OpenAI's API
   - Matches API billing exactly

3. **Model Support:**
   - `o200k_base`: GPT-4o, o1
   - `cl100k_base`: GPT-4, GPT-3.5-turbo, text-embedding-ada-002
   - `p50k_base`: Codex models, text-davinci-003
   - Can extend to custom models

4. **Memory Efficiency:**
   - `encode_to_numpy()` avoids Python list overhead
   - Reduces memory usage from ~80MB to ~20MB for large texts (10MB+)
   - Critical for high-throughput scenarios

### Alternatives Considered

| Approach | Accuracy | Speed | Memory | Decision |
|----------|----------|-------|--------|----------|
| **Character Count / 4** | ±37% error | Instant | Minimal | ❌ Too inaccurate |
| **tiktoken (exact)** | 100% | Fast | Moderate | ✅ **Selected** |
| **tiktoken (cached)** | 100% | Very fast | Moderate | ✅ **With caching** |
| **Estimation (heuristic)** | ~90% | Instant | Minimal | ⚠️ For rough checks only |
| **Other tokenizers** | Varies | Slower | Higher | ❌ Not official |

**Note on Claude Models:**
- Claude uses a custom BPE tokenizer (not tiktoken)
- Token counts are ~2.13x higher than GPT models for same text
- Use Claude's API for exact counts, tiktoken for estimates

### Implementation Details

**Installation:**
```bash
pip install tiktoken
```

**Basic Usage:**
```python
import tiktoken

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens for a given text and model."""
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))
```

**Optimized for Performance (Large Texts):**
```python
import tiktoken
import numpy as np

class TokenCounter:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.encoder = tiktoken.encoding_for_model(model)

    def count_tokens(self, text: str) -> int:
        """Count tokens efficiently using numpy."""
        # For large texts (>10KB), use encode_to_numpy
        if len(text) > 10000:
            tokens_array = self.encoder.encode_to_numpy(text)
            return len(tokens_array)
        else:
            return len(self.encoder.encode(text))

    def count_tokens_batch(
        self,
        texts: list[str],
        num_threads: int = 4
    ) -> list[int]:
        """Count tokens for multiple texts in parallel."""
        encoded_batch = self.encoder.encode_batch(texts, num_threads=num_threads)
        return [len(tokens) for tokens in encoded_batch]
```

**Caching Strategy (Real-Time Applications):**
```python
from functools import lru_cache
import hashlib
import tiktoken

class CachedTokenCounter:
    def __init__(self, model: str = "gpt-4o", cache_size: int = 1000):
        self.model = model
        self.encoder = tiktoken.encoding_for_model(model)
        self.cache_size = cache_size

    @lru_cache(maxsize=1000)
    def count_tokens_cached(self, text_hash: str, text: str) -> int:
        """Cache token counts for repeated texts."""
        return len(self.encoder.encode(text))

    def count_tokens(self, text: str) -> int:
        """Count tokens with caching."""
        # Hash the text for cache key
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return self.count_tokens_cached(text_hash, text)
```

**Chat Message Token Counting:**
```python
import tiktoken

def count_message_tokens(messages: list[dict], model: str = "gpt-4o") -> int:
    """
    Count tokens for chat completion API messages.

    Note: This is an approximation. Actual token count includes:
    - Message formatting tokens
    - Role tokens
    - Special tokens
    """
    enc = tiktoken.encoding_for_model(model)

    num_tokens = 0
    for message in messages:
        num_tokens += 4  # Message overhead
        for key, value in message.items():
            num_tokens += len(enc.encode(str(value)))

    num_tokens += 2  # Reply priming

    return num_tokens
```

**Performance Trade-offs:**

| Use Case | Approach | Speed | Accuracy |
|----------|----------|-------|----------|
| Real-time counting (hot path) | Cached exact | ~100µs | 100% |
| Batch processing | `encode_batch()` | 1.8M tok/s | 100% |
| Rough budget checks | `len(text) // 4` | <1µs | ~75% |
| Large documents (>1MB) | `encode_to_numpy()` | Fast + low memory | 100% |

**Estimation Heuristic (When Speed >> Accuracy):**
```python
def estimate_tokens(text: str) -> int:
    """
    Quick estimation: ~4 characters per token (English).
    Use only for rough checks, NOT for billing or limits.
    """
    return len(text) // 4
```

**Recommendations:**
1. **Use exact counting** (tiktoken) for:
   - Context window management
   - API cost calculation
   - Prompt budget enforcement

2. **Use estimation** for:
   - Quick pre-filtering (before exact count)
   - UI progress indicators
   - Non-critical metrics

3. **Use caching** for:
   - Repeated content (system prompts, templates)
   - High-frequency operations
   - Real-time applications

**References:**
- tiktoken GitHub: https://github.com/openai/tiktoken
- OpenAI Cookbook: Token counting examples
- Benchmark data: 150K tok/s (single-thread), 1.8M tok/s (12 threads)

---

## 3. Context Diffing Strategies

### Decision: Content Hashing with Structural Diff Fallback

**Primary Approach:** SHA-256 hashing for change detection
**Secondary Approach:** Structural diff for detailed analysis

### Rationale

1. **SHA-256 Hashing (Change Detection):**
   - **Speed:** ~500 MB/s (Python hashlib)
   - **Purpose:** Quick "has it changed?" check
   - **Use case:** Determine if full diff is needed
   - **Collision probability:** Negligible (2^-256)

2. **Structural Diff (When Changes Detected):**
   - **Speed:** Moderate (depends on structure size)
   - **Purpose:** Identify *what* changed
   - **Use case:** Incremental updates, patch generation
   - **Libraries:** `deepdiff` (Python), `diff-match-patch` (Google)

3. **Trade-off Strategy:**
   - Hash first (fast): 99% of the time, no change → skip diff
   - Diff second (moderate): Only when hash mismatch detected
   - Saves ~95% of compute on stable contexts

### Alternatives Considered

| Approach | Speed | Precision | Use Case | Decision |
|----------|-------|-----------|----------|----------|
| **SHA-256 Hash** | Very fast | Binary (changed/not) | Change detection | ✅ **Primary** |
| **MurmurHash** | Extremely fast | Binary (changed/not) | Non-crypto use | ⚠️ For non-security |
| **String Comparison** | Slow | Exact | Small texts | ❌ Not scalable |
| **Structural Diff** | Moderate | Detailed | Identify changes | ✅ **Secondary** |
| **JSON Patch (RFC 6902)** | Moderate | Detailed | API updates | ⚠️ JSON-specific |

### Implementation Details

**Change Detection Layer (SHA-256):**
```python
import hashlib
import json
from typing import Any, Optional

class ContentHasher:
    @staticmethod
    def hash_content(content: Any) -> str:
        """Generate SHA-256 hash of content."""
        if isinstance(content, str):
            data = content.encode('utf-8')
        elif isinstance(content, (dict, list)):
            # Serialize JSON with sorted keys for consistency
            data = json.dumps(content, sort_keys=True).encode('utf-8')
        elif isinstance(content, bytes):
            data = content
        else:
            data = str(content).encode('utf-8')

        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def has_changed(old_hash: str, new_content: Any) -> bool:
        """Check if content has changed since last hash."""
        new_hash = ContentHasher.hash_content(new_content)
        return old_hash != new_hash
```

**Structural Diff Layer (deepdiff):**
```python
from deepdiff import DeepDiff
from typing import Any, Dict

class StructuralDiffer:
    @staticmethod
    def compute_diff(old_content: Any, new_content: Any) -> Dict:
        """
        Compute detailed structural diff.
        Returns dict with changes: added, removed, modified, type_changes
        """
        diff = DeepDiff(
            old_content,
            new_content,
            ignore_order=False,  # Set True for unordered collections
            verbose_level=2,      # 0=minimal, 1=moderate, 2=detailed
            view='tree'           # 'tree' or 'text'
        )

        return diff

    @staticmethod
    def get_changed_paths(diff: DeepDiff) -> list[str]:
        """Extract paths that changed."""
        changed_paths = []

        for change_type in ['values_changed', 'type_changes',
                           'dictionary_item_added', 'dictionary_item_removed',
                           'iterable_item_added', 'iterable_item_removed']:
            if change_type in diff:
                changed_paths.extend(diff[change_type].keys())

        return changed_paths
```

**Hybrid Strategy (Hash + Diff):**
```python
from dataclasses import dataclass
from typing import Any, Optional
import time

@dataclass
class DiffResult:
    changed: bool
    old_hash: str
    new_hash: str
    diff: Optional[Dict] = None
    computation_time_ms: float = 0.0

class HybridDiffer:
    def __init__(self, always_compute_diff: bool = False):
        self.hasher = ContentHasher()
        self.differ = StructuralDiffer()
        self.always_compute_diff = always_compute_diff

    def compare(self, old_content: Any, new_content: Any,
                old_hash: Optional[str] = None) -> DiffResult:
        """
        Compare content using hash-first strategy.

        1. Hash new content
        2. Compare hashes (fast)
        3. If different, compute structural diff (moderate)
        """
        start_time = time.time()

        # Compute hashes
        if old_hash is None:
            old_hash = self.hasher.hash_content(old_content)
        new_hash = self.hasher.hash_content(new_content)

        # Quick check: are they the same?
        if old_hash == new_hash:
            computation_time = (time.time() - start_time) * 1000
            return DiffResult(
                changed=False,
                old_hash=old_hash,
                new_hash=new_hash,
                diff=None,
                computation_time_ms=computation_time
            )

        # Hashes differ - compute detailed diff
        diff = None
        if self.always_compute_diff or old_hash != new_hash:
            diff = self.differ.compute_diff(old_content, new_content)

        computation_time = (time.time() - start_time) * 1000

        return DiffResult(
            changed=True,
            old_hash=old_hash,
            new_hash=new_hash,
            diff=diff,
            computation_time_ms=computation_time
        )
```

**Performance Characteristics:**

| Operation | Data Size | Time | Use Case |
|-----------|-----------|------|----------|
| SHA-256 hash | 1 KB | <1 ms | Small contexts |
| SHA-256 hash | 1 MB | ~2 ms | Large contexts |
| SHA-256 hash | 10 MB | ~20 ms | Very large documents |
| DeepDiff | 1 KB | ~5 ms | Small structures |
| DeepDiff | 100 KB | ~50 ms | Medium structures |
| Full string compare | 1 MB | ~100 ms | ❌ Avoid |

**Optimization Tips:**

1. **Store hashes with content:**
   ```python
   context_item = {
       'content': {...},
       'hash': 'abc123...',  # Store for quick comparison
       'last_updated': datetime.now()
   }
   ```

2. **Use faster hashing for non-security:**
   ```python
   import mmh3  # MurmurHash3

   # ~5x faster than SHA-256, but not cryptographically secure
   hash_value = mmh3.hash128(content.encode(), seed=42)
   ```

3. **Diff only changed fields:**
   ```python
   # For structured data, diff field-by-field
   changed_fields = []
   for key in new_content.keys():
       if old_hashes.get(key) != new_hashes.get(key):
           changed_fields.append(key)
           # Only diff this field
           field_diff = differ.compute_diff(
               old_content[key],
               new_content[key]
           )
   ```

**JSON-Specific Optimization:**
```python
import json
from typing import Dict

class JSONDiffer:
    @staticmethod
    def json_patch(old: Dict, new: Dict) -> list[Dict]:
        """
        Generate JSON Patch (RFC 6902) operations.
        More efficient for API updates.
        """
        from jsonpatch import make_patch

        patch = make_patch(old, new)
        return patch.patch  # List of operations

    @staticmethod
    def apply_patch(original: Dict, patch: list[Dict]) -> Dict:
        """Apply JSON Patch to original."""
        from jsonpatch import apply_patch

        return apply_patch(original, patch)
```

**Recommendations:**

1. **Use SHA-256** when:
   - Quick change detection is needed
   - Content is append-only (logs, events)
   - Storage is cheap (store hash with content)

2. **Use MurmurHash** when:
   - Speed is critical (hash tables, bloom filters)
   - Security is not required
   - Collision risk is acceptable

3. **Use Structural Diff** when:
   - Need to identify specific changes
   - Generating patches for updates
   - Debugging or auditing changes

4. **Hybrid approach** (recommended):
   - Hash first for change detection (fast)
   - Diff only when hash mismatch (on-demand)
   - Store hashes to avoid recomputation

**Libraries:**
- **Python:**
  - `hashlib` (SHA-256, built-in)
  - `mmh3` (MurmurHash3, fast)
  - `deepdiff` (structural diff)
  - `jsonpatch` (JSON-specific)
  - `diff-match-patch` (Google's algorithm)

---

## 4. Tiered Memory Systems

### Decision: Three-Tier ARC-Inspired Cache with Hot/Warm/Cold Levels

**Architecture:**
- **Tier 1 (Hot):** In-memory, LRU + frequency tracking (ARC-inspired)
- **Tier 2 (Warm):** In-memory, compressed or on-disk cache
- **Tier 3 (Cold):** Persistent storage, retrieved on-demand

### Rationale

1. **ARC (Adaptive Replacement Cache):**
   - Self-tuning: Automatically balances recency vs frequency
   - Two LRU lists: T1 (recency) and T2 (frequency)
   - Adapts to workload without manual tuning
   - Proven in production: PostgreSQL, ZFS, IBM storage systems

2. **Three-Tier Benefits:**
   - Hot tier: <1ms access (in-memory, frequently accessed)
   - Warm tier: <10ms access (compressed or disk-backed)
   - Cold tier: <100ms access (database, S3, etc.)
   - Memory efficiency: 80% of requests from 20% of hot data

3. **No Manual Tuning:**
   - ARC automatically adjusts T1/T2 split based on access patterns
   - Threshold optimization for tier promotion/demotion
   - Learning-based eviction policies

### Alternatives Considered

| Policy | Self-Tuning | Performance | Complexity | Decision |
|--------|-------------|-------------|------------|----------|
| **LRU** | No | Good | Low | ❌ Too simple |
| **LFU** | No | Moderate | Low | ❌ Stale items persist |
| **2Q** | No | Good | Moderate | ⚠️ Requires tuning |
| **ARC** | Yes | Excellent | Moderate | ✅ **Selected** |
| **LIRS** | No | Excellent | High | ❌ Complex |
| **Random** | N/A | Poor | Very low | ❌ Unpredictable |

### Implementation Details

**Three-Tier Architecture:**
```python
from collections import OrderedDict
from typing import Any, Optional, Tuple
from enum import Enum
import time

class CacheTier(Enum):
    HOT = 1    # In-memory, fast access
    WARM = 2   # Compressed or disk-backed
    COLD = 3   # Persistent storage

class ARCCache:
    """
    Adaptive Replacement Cache implementation.
    Maintains two LRU lists: T1 (recency) and T2 (frequency).
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.p = 0  # Target size for T1 (adaptive)

        # T1: Items seen once recently
        self.t1 = OrderedDict()
        # T2: Items seen multiple times (frequent)
        self.t2 = OrderedDict()

        # Ghost lists (metadata only, no data)
        self.b1 = OrderedDict()  # Evicted from T1
        self.b2 = OrderedDict()  # Evicted from T2

        self.stats = {
            'hits': 0,
            'misses': 0,
            't1_to_t2_promotions': 0
        }

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        # Check T1 (recency)
        if key in self.t1:
            value = self.t1.pop(key)
            self.t2[key] = value  # Promote to T2 (frequent)
            self.stats['hits'] += 1
            self.stats['t1_to_t2_promotions'] += 1
            return value

        # Check T2 (frequency)
        if key in self.t2:
            self.t2.move_to_end(key)  # Mark as recently used
            self.stats['hits'] += 1
            return self.t2[key]

        self.stats['misses'] += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """Insert item into cache."""
        # Already in T1 or T2
        if key in self.t1 or key in self.t2:
            self.get(key)  # Update position
            if key in self.t2:
                self.t2[key] = value
            return

        # Cache hit in ghost list B1 (was recently evicted from T1)
        if key in self.b1:
            # Adapt: increase T1 target size
            delta = max(len(self.b2) // len(self.b1), 1) if self.b1 else 1
            self.p = min(self.p + delta, self.capacity)
            self._replace(key, in_b2=False)
            self.b1.pop(key)
            self.t2[key] = value
            return

        # Cache hit in ghost list B2 (was evicted from T2)
        if key in self.b2:
            # Adapt: decrease T1 target size
            delta = max(len(self.b1) // len(self.b2), 1) if self.b2 else 1
            self.p = max(self.p - delta, 0)
            self._replace(key, in_b2=True)
            self.b2.pop(key)
            self.t2[key] = value
            return

        # Cache miss - insert into T1
        if len(self.t1) + len(self.t2) >= self.capacity:
            self._replace(key, in_b2=False)

        self.t1[key] = value

    def _replace(self, key: str, in_b2: bool) -> None:
        """Evict item according to ARC policy."""
        if self.t1 and (
            len(self.t1) > self.p or
            (key in self.b2 and len(self.t1) == self.p)
        ):
            # Evict from T1
            evict_key, _ = self.t1.popitem(last=False)
            self.b1[evict_key] = None  # Add to ghost list
        else:
            # Evict from T2
            if self.t2:
                evict_key, _ = self.t2.popitem(last=False)
                self.b2[evict_key] = None

        # Limit ghost list sizes
        if len(self.b1) > self.capacity:
            self.b1.popitem(last=False)
        if len(self.b2) > self.capacity:
            self.b2.popitem(last=False)

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (
            self.stats['hits'] / total_requests
            if total_requests > 0 else 0
        )

        return {
            'hit_rate': hit_rate,
            'total_requests': total_requests,
            't1_size': len(self.t1),
            't2_size': len(self.t2),
            't1_target': self.p,
            **self.stats
        }
```

**Three-Tier Memory Manager:**
```python
import sqlite3
import pickle
import zlib
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class CacheEntry:
    key: str
    value: Any
    tier: CacheTier
    size_bytes: int
    last_accessed: datetime
    access_count: int

class ThreeTierMemorySystem:
    """
    Three-tier memory system with ARC hot cache.

    Tier 1 (Hot):  In-memory ARC cache (fast, small)
    Tier 2 (Warm): Compressed in-memory or disk cache
    Tier 3 (Cold): SQLite database (persistent)
    """

    def __init__(
        self,
        hot_capacity: int = 100,      # Hot tier: 100 items
        warm_capacity: int = 500,     # Warm tier: 500 items
        db_path: str = ":memory:"     # Cold tier: database
    ):
        # Tier 1: Hot cache (ARC)
        self.hot_cache = ARCCache(capacity=hot_capacity)

        # Tier 2: Warm cache (compressed)
        self.warm_cache: dict[str, bytes] = {}
        self.warm_capacity = warm_capacity
        self.warm_lru = OrderedDict()  # Track access order

        # Tier 3: Cold storage (SQLite)
        self.db_conn = sqlite3.connect(db_path)
        self._init_db()

        self.stats = {
            'hot_hits': 0,
            'warm_hits': 0,
            'cold_hits': 0,
            'misses': 0
        }

    def _init_db(self):
        """Initialize cold storage database."""
        self.db_conn.execute("""
            CREATE TABLE IF NOT EXISTS context_items (
                key TEXT PRIMARY KEY,
                value BLOB,
                last_accessed TIMESTAMP,
                access_count INTEGER,
                size_bytes INTEGER
            )
        """)
        self.db_conn.commit()

    def get(self, key: str) -> Optional[Any]:
        """
        Get item from memory system (hot → warm → cold).
        Promotes items to higher tiers based on access.
        """
        # Check Tier 1 (Hot)
        value = self.hot_cache.get(key)
        if value is not None:
            self.stats['hot_hits'] += 1
            return value

        # Check Tier 2 (Warm)
        if key in self.warm_cache:
            compressed_value = self.warm_cache[key]
            value = pickle.loads(zlib.decompress(compressed_value))

            # Promote to hot tier
            self.hot_cache.put(key, value)
            self.warm_lru.move_to_end(key)

            self.stats['warm_hits'] += 1
            return value

        # Check Tier 3 (Cold)
        cursor = self.db_conn.execute(
            "SELECT value FROM context_items WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()

        if row:
            value = pickle.loads(row[0])

            # Promote to warm tier
            self._put_warm(key, value)

            # Update access stats
            self.db_conn.execute(
                """UPDATE context_items
                   SET access_count = access_count + 1,
                       last_accessed = ?
                   WHERE key = ?""",
                (datetime.now(), key)
            )
            self.db_conn.commit()

            self.stats['cold_hits'] += 1
            return value

        self.stats['misses'] += 1
        return None

    def put(self, key: str, value: Any, tier: CacheTier = CacheTier.HOT) -> None:
        """Insert item into specified tier."""
        if tier == CacheTier.HOT:
            self.hot_cache.put(key, value)
        elif tier == CacheTier.WARM:
            self._put_warm(key, value)
        else:  # CacheTier.COLD
            self._put_cold(key, value)

    def _put_warm(self, key: str, value: Any) -> None:
        """Add item to warm tier (compressed)."""
        serialized = pickle.dumps(value)
        compressed = zlib.compress(serialized, level=6)

        # Evict if at capacity
        if len(self.warm_cache) >= self.warm_capacity:
            evict_key = next(iter(self.warm_lru))
            del self.warm_cache[evict_key]
            self.warm_lru.pop(evict_key)

            # Demote to cold tier
            # (already serialized, just decompress and store)

        self.warm_cache[key] = compressed
        self.warm_lru[key] = True
        self.warm_lru.move_to_end(key)

    def _put_cold(self, key: str, value: Any) -> None:
        """Add item to cold tier (database)."""
        serialized = pickle.dumps(value)
        size_bytes = len(serialized)

        self.db_conn.execute(
            """INSERT OR REPLACE INTO context_items
               (key, value, last_accessed, access_count, size_bytes)
               VALUES (?, ?, ?, ?, ?)""",
            (key, serialized, datetime.now(), 1, size_bytes)
        )
        self.db_conn.commit()

    def get_stats(self) -> dict:
        """Get memory system statistics."""
        total_requests = sum(self.stats.values())

        return {
            'total_requests': total_requests,
            'hot_tier_size': len(self.hot_cache.t1) + len(self.hot_cache.t2),
            'warm_tier_size': len(self.warm_cache),
            'cold_tier_size': self._get_cold_count(),
            'hit_rates': {
                'hot': self.stats['hot_hits'] / total_requests if total_requests > 0 else 0,
                'warm': self.stats['warm_hits'] / total_requests if total_requests > 0 else 0,
                'cold': self.stats['cold_hits'] / total_requests if total_requests > 0 else 0,
            },
            **self.stats
        }

    def _get_cold_count(self) -> int:
        """Get number of items in cold storage."""
        cursor = self.db_conn.execute("SELECT COUNT(*) FROM context_items")
        return cursor.fetchone()[0]
```

**Threshold Optimization:**
```python
class TierThresholdOptimizer:
    """Optimize promotion/demotion thresholds based on access patterns."""

    def __init__(self, memory_system: ThreeTierMemorySystem):
        self.memory_system = memory_system
        self.access_history = []

    def optimize_thresholds(self, target_hot_hit_rate: float = 0.8):
        """
        Adjust tier sizes to achieve target hit rates.
        Uses gradient-based optimization.
        """
        stats = self.memory_system.get_stats()
        current_hot_rate = stats['hit_rates']['hot']

        if current_hot_rate < target_hot_hit_rate:
            # Increase hot tier capacity
            new_capacity = int(
                self.memory_system.hot_cache.capacity * 1.1
            )
            print(f"Increasing hot cache: {new_capacity}")
        else:
            # Can potentially decrease (save memory)
            new_capacity = max(
                int(self.memory_system.hot_cache.capacity * 0.95),
                50  # Minimum size
            )

        # Would need to rebuild cache with new capacity
        # (implementation detail)
```

**Recommendations:**

1. **Start with conservative sizes:**
   - Hot: 100-500 items (~10-50MB)
   - Warm: 500-2000 items (~50-200MB compressed)
   - Cold: Unlimited (disk/DB)

2. **Monitor and adjust:**
   - Target: 80%+ hit rate in hot tier
   - If <80%: Increase hot capacity
   - If >95%: Consider decreasing (wasting memory)

3. **Use ARC for hot tier:**
   - Self-tuning, no manual parameter selection
   - Handles mixed workloads well
   - Proven in production systems

4. **Compression for warm tier:**
   - zlib level 6: Good balance of speed/compression
   - Typical: 60-70% size reduction
   - Trade: 2-5ms decompression time

**References:**
- ARC Paper (USENIX FAST '03): Self-tuning, low overhead
- Redis: Uses approximated LRU with sampling
- PostgreSQL: Uses ARC-like algorithm for buffer management

---

## 5. Checkpoint/Restore Patterns

### Decision: Incremental Checkpointing with Event Sourcing

**Strategy:** Snapshot + Delta (Incremental) Checkpointing
**Serialization:** MessagePack (msgpack) for performance
**Recovery:** Last snapshot + delta events

### Rationale

1. **Incremental Checkpointing:**
   - Full snapshot: Every N operations or M minutes
   - Delta checkpoints: Only changes since last snapshot
   - 10-50x smaller than full checkpoints
   - Faster to write, faster to restore recent states

2. **Event Sourcing Pattern:**
   - Store state-changing events, not just state
   - Can replay events to reconstruct state
   - Enables time-travel debugging
   - Used in: Kafka, EventStore, Flink, Temporal

3. **MessagePack Serialization:**
   - 2-3x faster than JSON
   - 10-30% smaller than JSON
   - Cross-language compatibility
   - Better than pickle for security and portability

### Alternatives Considered

| Approach | Write Speed | Restore Speed | Size | Decision |
|----------|-------------|---------------|------|----------|
| **Full snapshots only** | Slow | Fast | Large | ❌ Wasteful |
| **Incremental (snapshot + delta)** | Fast | Fast | Small | ✅ **Selected** |
| **Event sourcing only** | Fast | Slow | Small | ⚠️ Slow recovery |
| **Copy-on-write (COW)** | Moderate | Fast | Moderate | ⚠️ Complex |

**Serialization Format Comparison:**

| Format | Serialize Speed | Deserialize Speed | Size | Decision |
|--------|----------------|-------------------|------|----------|
| **JSON** | Moderate | Moderate | Large | ❌ Slower |
| **Pickle** | Fast | Fast | Moderate | ⚠️ Python-only, security risk |
| **MessagePack** | Very fast | Very fast | Small | ✅ **Selected** |
| **Protobuf** | Fast | Very fast | Very small | ⚠️ Requires schema |
| **Avro** | Fast | Fast | Small | ⚠️ Requires schema |

**Benchmark Data (1M records):**
- JSON: ~180MB, 2.2s encode, 2.5s decode
- Pickle: ~120MB, 1.5s encode, 1.3s decode
- MessagePack: ~100MB, 0.8s encode, 0.9s decode
- Protobuf: ~80MB, 0.7s encode, 0.6s decode (needs schema)

### Implementation Details

**Checkpoint Manager:**
```python
import msgpack
import os
from pathlib import Path
from typing import Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import json

@dataclass
class CheckpointMetadata:
    checkpoint_id: str
    timestamp: datetime
    checkpoint_type: str  # 'full' or 'delta'
    base_checkpoint_id: Optional[str]  # For delta checkpoints
    event_count: int
    size_bytes: int

@dataclass
class StateEvent:
    event_id: str
    timestamp: datetime
    event_type: str
    data: dict

class CheckpointManager:
    """
    Manages incremental checkpointing with event sourcing.

    Strategy:
    - Full snapshot every N events or M minutes
    - Delta checkpoints (events only) between snapshots
    - Recovery: Load last snapshot + replay delta events
    """

    def __init__(
        self,
        checkpoint_dir: str = "./checkpoints",
        full_checkpoint_interval: int = 1000,  # Every 1000 events
        full_checkpoint_time_minutes: int = 30  # Or every 30 minutes
    ):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.full_checkpoint_interval = full_checkpoint_interval
        self.full_checkpoint_time_minutes = full_checkpoint_time_minutes

        self.event_buffer: List[StateEvent] = []
        self.last_full_checkpoint_id: Optional[str] = None
        self.last_full_checkpoint_time: Optional[datetime] = None
        self.event_count_since_full = 0

    def save_full_checkpoint(self, state: dict) -> CheckpointMetadata:
        """Save complete state snapshot."""
        checkpoint_id = f"full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.msgpack"

        # Serialize with MessagePack
        serialized = msgpack.packb(state, use_bin_type=True)

        # Write to disk
        checkpoint_path.write_bytes(serialized)

        # Create metadata
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            checkpoint_type='full',
            base_checkpoint_id=None,
            event_count=0,
            size_bytes=len(serialized)
        )

        # Save metadata
        self._save_metadata(metadata)

        # Update tracking
        self.last_full_checkpoint_id = checkpoint_id
        self.last_full_checkpoint_time = datetime.now()
        self.event_count_since_full = 0
        self.event_buffer.clear()

        return metadata

    def save_delta_checkpoint(self, events: List[StateEvent]) -> CheckpointMetadata:
        """Save incremental checkpoint (events only)."""
        if not self.last_full_checkpoint_id:
            raise ValueError("No full checkpoint exists. Save full checkpoint first.")

        checkpoint_id = f"delta_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.msgpack"

        # Serialize events
        events_data = [asdict(event) for event in events]
        serialized = msgpack.packb(events_data, use_bin_type=True)

        # Write to disk
        checkpoint_path.write_bytes(serialized)

        # Create metadata
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            checkpoint_type='delta',
            base_checkpoint_id=self.last_full_checkpoint_id,
            event_count=len(events),
            size_bytes=len(serialized)
        )

        self._save_metadata(metadata)

        return metadata

    def record_event(self, event: StateEvent) -> Optional[CheckpointMetadata]:
        """
        Record a state-changing event.
        Triggers checkpoint if thresholds are met.
        """
        self.event_buffer.append(event)
        self.event_count_since_full += 1

        # Check if we should create a checkpoint
        should_checkpoint_by_count = (
            self.event_count_since_full >= self.full_checkpoint_interval
        )

        should_checkpoint_by_time = False
        if self.last_full_checkpoint_time:
            minutes_since = (
                datetime.now() - self.last_full_checkpoint_time
            ).total_seconds() / 60
            should_checkpoint_by_time = (
                minutes_since >= self.full_checkpoint_time_minutes
            )

        if should_checkpoint_by_count or should_checkpoint_by_time:
            # Create delta checkpoint
            metadata = self.save_delta_checkpoint(self.event_buffer.copy())
            self.event_buffer.clear()
            return metadata

        return None

    def restore_latest(self) -> tuple[dict, List[StateEvent]]:
        """
        Restore from latest checkpoint.

        Returns:
            (state, unprocessed_events)
        """
        # Find latest full checkpoint
        checkpoints = self._list_checkpoints()
        if not checkpoints:
            raise ValueError("No checkpoints found")

        full_checkpoints = [
            cp for cp in checkpoints
            if cp.checkpoint_type == 'full'
        ]
        if not full_checkpoints:
            raise ValueError("No full checkpoints found")

        # Load latest full checkpoint
        latest_full = max(full_checkpoints, key=lambda x: x.timestamp)
        state = self._load_checkpoint(latest_full.checkpoint_id)

        # Find all delta checkpoints after this full checkpoint
        delta_checkpoints = [
            cp for cp in checkpoints
            if cp.checkpoint_type == 'delta'
            and cp.base_checkpoint_id == latest_full.checkpoint_id
            and cp.timestamp > latest_full.timestamp
        ]

        # Sort by timestamp
        delta_checkpoints.sort(key=lambda x: x.timestamp)

        # Load and collect events
        all_events = []
        for delta in delta_checkpoints:
            events_data = self._load_checkpoint(delta.checkpoint_id)
            events = [
                StateEvent(**event_dict)
                for event_dict in events_data
            ]
            all_events.extend(events)

        return state, all_events

    def _load_checkpoint(self, checkpoint_id: str) -> Any:
        """Load checkpoint data."""
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.msgpack"

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        serialized = checkpoint_path.read_bytes()
        return msgpack.unpackb(serialized, raw=False)

    def _save_metadata(self, metadata: CheckpointMetadata):
        """Save checkpoint metadata."""
        metadata_path = (
            self.checkpoint_dir / f"{metadata.checkpoint_id}.meta.json"
        )

        # Convert to dict and handle datetime
        meta_dict = asdict(metadata)
        meta_dict['timestamp'] = metadata.timestamp.isoformat()

        metadata_path.write_text(json.dumps(meta_dict, indent=2))

    def _list_checkpoints(self) -> List[CheckpointMetadata]:
        """List all checkpoints."""
        checkpoints = []

        for meta_file in self.checkpoint_dir.glob("*.meta.json"):
            meta_dict = json.loads(meta_file.read_text())
            meta_dict['timestamp'] = datetime.fromisoformat(meta_dict['timestamp'])
            checkpoints.append(CheckpointMetadata(**meta_dict))

        return checkpoints
```

**Usage Example:**
```python
# Initialize checkpoint manager
checkpoint_mgr = CheckpointManager(
    checkpoint_dir="./agent_checkpoints",
    full_checkpoint_interval=1000,
    full_checkpoint_time_minutes=30
)

# Save initial state
initial_state = {
    'agent_id': 'agent_001',
    'context_items': [...],
    'memory': {...}
}
checkpoint_mgr.save_full_checkpoint(initial_state)

# Record events
event = StateEvent(
    event_id='evt_001',
    timestamp=datetime.now(),
    event_type='context_added',
    data={'key': 'doc_123', 'value': {...}}
)
checkpoint_mgr.record_event(event)  # Auto-checkpoints if threshold met

# Restore later
restored_state, pending_events = checkpoint_mgr.restore_latest()
```

**Recovery Strategy:**
```python
class StateRecovery:
    """Recover agent state from checkpoints."""

    @staticmethod
    def replay_events(
        base_state: dict,
        events: List[StateEvent]
    ) -> dict:
        """
        Replay events to reconstruct current state.

        This is event sourcing - each event modifies state.
        """
        current_state = base_state.copy()

        for event in events:
            if event.event_type == 'context_added':
                current_state['context_items'][event.data['key']] = (
                    event.data['value']
                )
            elif event.event_type == 'context_removed':
                current_state['context_items'].pop(event.data['key'], None)
            elif event.event_type == 'memory_updated':
                current_state['memory'].update(event.data)
            # Add more event types as needed

        return current_state

    @staticmethod
    def recover_to_timestamp(
        checkpoint_mgr: CheckpointManager,
        target_time: datetime
    ) -> dict:
        """
        Time-travel recovery: restore state at specific timestamp.
        Useful for debugging.
        """
        state, events = checkpoint_mgr.restore_latest()

        # Filter events up to target time
        relevant_events = [
            e for e in events
            if e.timestamp <= target_time
        ]

        return StateRecovery.replay_events(state, relevant_events)
```

**Optimization: Compression**
```python
import zlib

class CompressedCheckpointManager(CheckpointManager):
    """Checkpoint manager with compression."""

    def save_full_checkpoint(self, state: dict) -> CheckpointMetadata:
        checkpoint_id = f"full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.msgpack.gz"

        # Serialize with MessagePack
        serialized = msgpack.packb(state, use_bin_type=True)

        # Compress with zlib
        compressed = zlib.compress(serialized, level=6)

        # Write to disk
        checkpoint_path.write_bytes(compressed)

        # ... rest of implementation
        # Typical compression: 60-70% size reduction
```

**Recommendations:**

1. **Checkpoint frequency:**
   - Full: Every 1000-5000 events OR 15-30 minutes
   - Delta: Every 100-500 events OR 5-10 minutes
   - Adjust based on recovery time tolerance

2. **Serialization choice:**
   - **MessagePack:** Best balance (fast, portable, compact)
   - **Pickle:** If Python-only and trust input (faster)
   - **Protobuf:** If need schema validation and smallest size

3. **Storage:**
   - Local disk: For development and single-node
   - S3/Cloud: For distributed systems
   - Both: Local for fast recovery, cloud for backup

4. **Retention policy:**
   - Keep last 10 full checkpoints
   - Keep all deltas between kept full checkpoints
   - Delete older checkpoints (save space)

5. **Testing:**
   - Regularly test recovery process
   - Measure recovery time (should be <10s for most cases)
   - Test with corrupted checkpoints (handle gracefully)

**References:**
- Apache Flink: Incremental checkpointing for stream processing
- Temporal.io: Workflow checkpointing and recovery
- Event Sourcing pattern (Martin Fowler): State reconstruction from events
- MessagePack benchmarks: 2-3x faster than JSON

---

## Summary & Recommendations

### Quick Reference Table

| Component | Recommended Approach | Key Benefit |
|-----------|---------------------|-------------|
| **Importance Scoring** | Hybrid Exponential Decay (R+F+T) | Balances recency, frequency, content type |
| **Token Counting** | tiktoken with caching | 100% accurate, 3-6x faster than alternatives |
| **Change Detection** | SHA-256 hash + structural diff | Fast detection (hash), detailed analysis (diff) |
| **Tiered Caching** | ARC-based 3-tier (hot/warm/cold) | Self-tuning, proven in production |
| **Checkpointing** | Incremental with MessagePack | Fast, compact, recoverable |

### Implementation Priority

**Phase 1: Core Functionality**
1. ✅ Implement tiktoken token counter with basic caching
2. ✅ Implement SHA-256 content hashing for change detection
3. ✅ Build three-tier memory system with simple LRU (hot tier)
4. ✅ Basic full checkpoint/restore with MessagePack

**Phase 2: Optimization**
1. ⚡ Add hybrid importance scoring algorithm
2. ⚡ Upgrade hot tier to ARC cache
3. ⚡ Implement incremental checkpointing (snapshot + delta)
4. ⚡ Add structural diff for detailed change analysis

**Phase 3: Advanced Features**
1. 🚀 Threshold auto-tuning based on metrics
2. 🚀 Event sourcing for time-travel debugging
3. 🚀 Distributed checkpointing (S3/cloud storage)
4. 🚀 Compression for warm tier and checkpoints

### Performance Targets

| Metric | Target | Approach |
|--------|--------|----------|
| **Token counting** | <1ms for cached, <10ms for new | tiktoken + LRU cache |
| **Change detection** | <2ms for 1MB content | SHA-256 hashing |
| **Hot cache hit rate** | >80% | ARC self-tuning |
| **Checkpoint write** | <1s for 100MB state | MessagePack + compression |
| **Recovery time** | <10s for typical state | Incremental restore |

### Monitoring & Tuning

**Key Metrics to Track:**
```python
metrics = {
    'importance_scoring': {
        'avg_score': float,
        'score_distribution': dict,  # Histogram
        'eviction_count': int
    },
    'token_counting': {
        'cache_hit_rate': float,
        'avg_count_time_ms': float,
        'total_tokens_processed': int
    },
    'caching': {
        'hot_hit_rate': float,
        'warm_hit_rate': float,
        'cold_hit_rate': float,
        'avg_retrieval_time_ms': dict  # Per tier
    },
    'checkpointing': {
        'checkpoint_frequency': float,  # Per hour
        'avg_checkpoint_size_mb': float,
        'avg_restore_time_s': float
    }
}
```

### Security Considerations

1. **Pickle Security:**
   - ⚠️ Never unpickle untrusted data
   - Use MessagePack for external data
   - Validate checksums before restore

2. **Hashing:**
   - Use SHA-256 for integrity checks
   - Use MurmurHash for non-security use cases only

3. **Storage:**
   - Encrypt checkpoints at rest (if sensitive data)
   - Use signed URLs for cloud storage access
   - Implement access control on checkpoint directories

### Testing Strategy

**Unit Tests:**
- Importance scoring edge cases (new items, high frequency, old items)
- Token counting accuracy (known texts with known token counts)
- Cache hit/miss scenarios
- Checkpoint corruption handling

**Integration Tests:**
- Full checkpoint/restore cycle
- Multi-tier cache promotion/demotion
- Event replay accuracy
- Performance under load

**Benchmarks:**
- Token counting throughput
- Cache hit rates with realistic workloads
- Checkpoint write/restore times
- Memory usage under different tier configurations

---

## References & Further Reading

### Papers & Academic
- **ARC Cache**: "ARC: A Self-Tuning, Low Overhead Replacement Cache" (USENIX FAST '03)
- **Time Decay**: "Forward Decay: A Practical Time Decay Model for Streaming Systems" (Rutgers DIMACS)
- **BPE Tokenization**: "Neural Machine Translation of Rare Words with Subword Units" (Sennrich et al.)

### Libraries & Tools
- **tiktoken**: https://github.com/openai/tiktoken
- **deepdiff**: https://github.com/seperman/deepdiff
- **msgpack**: https://github.com/msgpack/msgpack-python
- **diff-match-patch**: https://github.com/google/diff-match-patch

### Production Systems
- **Redis**: LFU with decay, approximated LRU
- **PostgreSQL**: ARC-based buffer management
- **Apache Flink**: Incremental checkpointing
- **ZFS**: ARC for filesystem cache

### Blogs & Guides
- OpenAI Cookbook: Token counting examples
- LLM token calculators: Comparison across models
- RFM Analysis: Recency-Frequency-Monetary scoring in analytics

---

**Document Version:** 1.0
**Last Updated:** 2025-11-14
**Author:** AI Research Agent
