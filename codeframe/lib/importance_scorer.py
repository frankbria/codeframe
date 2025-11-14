"""Importance scoring for context items (T029).

Calculates importance scores using hybrid exponential decay algorithm:
    score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost

Where:
- Type weight: Content type importance (TASK=1.0, CODE=0.8, ERROR=0.7, etc.)
- Age decay: Exponential decay over time (e^(-λ × age_days), λ=0.5)
- Access boost: Log-normalized access frequency (log(count + 1) / 10, capped at 1.0)

Part of 007-context-management Phase 4 (US2 - Importance Scoring).
"""

import math
from datetime import datetime, UTC
from typing import Dict


# Content type weights for importance scoring
# Higher weight = more important
ITEM_TYPE_WEIGHTS: Dict[str, float] = {
    'TASK': 1.0,        # Highest priority - current work
    'CODE': 0.8,        # High priority - implementation details
    'ERROR': 0.7,       # High priority - must track failures
    'TEST_RESULT': 0.6, # Medium priority - validation results
    'PRD_SECTION': 0.5  # Medium priority - requirements context
}

# Decay rate for age component (λ in exponential decay formula)
# λ=0.5 gives half-life of ~1.4 days
DECAY_RATE = 0.5

# Weights for score components (must sum to 1.0)
WEIGHT_TYPE = 0.4      # 40% weight on content type
WEIGHT_AGE = 0.4       # 40% weight on recency
WEIGHT_ACCESS = 0.2    # 20% weight on access frequency


def calculate_age_decay(created_at: datetime) -> float:
    """Calculate age decay component using exponential decay.

    Formula: e^(-λ × age_days)
    Where λ (DECAY_RATE) = 0.5

    Args:
        created_at: Timestamp when item was created

    Returns:
        float: Decay value in range [0.0, 1.0]
            - 1.0 for brand new items (age=0)
            - Approaches 0.0 for very old items
            - 0.5 at half-life (~1.4 days for λ=0.5)
    """
    # Calculate age in days
    age_days = (datetime.now(UTC) - created_at).total_seconds() / 86400

    # Handle edge case: future dates (should not happen, but be defensive)
    if age_days < 0:
        age_days = 0

    # Exponential decay: e^(-λt)
    decay = math.exp(-DECAY_RATE * age_days)

    return decay


def calculate_access_boost(access_count: int) -> float:
    """Calculate access frequency boost using logarithmic normalization.

    Formula: log(access_count + 1) / 10, capped at 1.0

    Logarithmic scaling prevents high-frequency items from dominating
    while still rewarding frequent access (diminishing returns).

    Args:
        access_count: Number of times item has been accessed

    Returns:
        float: Access boost in range [0.0, 1.0]
            - 0.0 for never accessed (count=0)
            - 0.23 for count=9 (log(10)/10)
            - 0.46 for count=99 (log(100)/10)
            - Capped at 1.0 for very high counts
    """
    if access_count < 0:
        access_count = 0

    # Logarithmic normalization
    boost = math.log(access_count + 1) / 10

    # Cap at 1.0
    return min(boost, 1.0)


def calculate_importance_score(
    item_type: str,
    created_at: datetime,
    access_count: int,
    last_accessed: datetime
) -> float:
    """Calculate importance score for a context item.

    Combines three components with weighted sum:
    - Type weight (40%): Importance based on content type
    - Age decay (40%): Recency using exponential decay
    - Access boost (20%): Frequency using logarithmic scaling

    Args:
        item_type: Type of context item (TASK, CODE, ERROR, etc.)
        created_at: When item was created
        access_count: Number of times accessed
        last_accessed: When item was last accessed (unused in current formula)

    Returns:
        float: Importance score in range [0.0, 1.0]
            - Higher score = more important
            - Used for tier assignment (HOT >= 0.8, WARM >= 0.4, COLD < 0.4)

    Examples:
        >>> # New TASK with no accesses
        >>> calculate_importance_score(
        ...     'TASK',
        ...     datetime.now(UTC),
        ...     0,
        ...     datetime.now(UTC)
        ... )
        0.8  # 0.4 × 1.0 + 0.4 × 1.0 + 0.2 × 0.0

        >>> # 7-day-old CODE with 100 accesses
        >>> calculate_importance_score(
        ...     'CODE',
        ...     datetime.now(UTC) - timedelta(days=7),
        ...     100,
        ...     datetime.now(UTC)
        ... )
        0.42  # 0.4 × 0.8 + 0.4 × 0.03 + 0.2 × 0.46
    """
    # Component 1: Type weight
    type_weight = ITEM_TYPE_WEIGHTS.get(item_type, 0.5)  # Default to 0.5 if unknown

    # Component 2: Age decay
    age_decay = calculate_age_decay(created_at)

    # Component 3: Access boost
    access_boost = calculate_access_boost(access_count)

    # Weighted combination
    score = (
        WEIGHT_TYPE * type_weight +
        WEIGHT_AGE * age_decay +
        WEIGHT_ACCESS * access_boost
    )

    # Clamp to [0.0, 1.0] range (should already be in range, but be defensive)
    return max(0.0, min(score, 1.0))


def assign_tier(importance_score: float) -> str:
    """Assign tier based on importance score (T039).

    Tier assignment thresholds:
    - HOT: score >= 0.8 (always loaded, critical recent context)
    - WARM: 0.4 <= score < 0.8 (on-demand loading)
    - COLD: score < 0.4 (archived, rarely accessed)

    Args:
        importance_score: Calculated importance score in range [0.0, 1.0]

    Returns:
        str: Tier assignment ('HOT', 'WARM', or 'COLD')

    Examples:
        >>> assign_tier(0.9)
        'HOT'
        >>> assign_tier(0.6)
        'WARM'
        >>> assign_tier(0.2)
        'COLD'
        >>> assign_tier(0.8)  # Exact boundary
        'HOT'
        >>> assign_tier(0.4)  # Exact boundary
        'WARM'
    """
    # HOT tier: score >= 0.8
    if importance_score >= 0.8:
        return "HOT"

    # WARM tier: 0.4 <= score < 0.8
    if importance_score >= 0.4:
        return "WARM"

    # COLD tier: score < 0.4
    return "COLD"
