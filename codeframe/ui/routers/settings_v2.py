"""V2 Settings router — agent settings managed via the web UI.

Reads/writes a flat AgentSettings shape persisted in
.codeframe/config.yaml via load_environment_config / save_environment_config.

Routes:
    GET /api/v2/settings  - Load agent settings (returns defaults if missing)
    PUT /api/v2/settings  - Save agent settings (merges into existing config)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from codeframe.core.config import (
    EnvironmentConfig,
    load_environment_config,
    save_environment_config,
)
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.models import (
    AGENT_TYPES,
    AgentSettingsResponse,
    AgentTypeModelConfig,
    UpdateAgentSettingsRequest,
)
from codeframe.ui.response_models import ErrorCodes, api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])


def _config_to_response(config: EnvironmentConfig) -> AgentSettingsResponse:
    """Map an EnvironmentConfig to the flat AgentSettings response shape."""
    saved_models = config.agent_type_models or {}
    agent_models = [
        AgentTypeModelConfig(
            agent_type=agent_type,
            default_model=saved_models.get(agent_type, ""),
        )
        for agent_type in AGENT_TYPES
    ]
    return AgentSettingsResponse(
        agent_models=agent_models,
        max_turns=config.agent_budget.max_iterations,
        max_cost_usd=config.max_cost_usd,
    )


@router.get("", response_model=AgentSettingsResponse)
@rate_limit_standard()
async def get_settings(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> AgentSettingsResponse:
    """Load agent settings for the workspace.

    Returns defaults if no .codeframe/config.yaml exists.
    """
    try:
        config = load_environment_config(workspace.repo_path) or EnvironmentConfig()
        return _config_to_response(config)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to load settings", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )


@router.put("", response_model=AgentSettingsResponse)
@rate_limit_standard()
async def update_settings(
    request: Request,
    body: UpdateAgentSettingsRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> AgentSettingsResponse:
    """Save agent settings.

    Merges into existing EnvironmentConfig so unrelated fields
    (package_manager, test_framework, etc.) are preserved.
    """
    try:
        config = load_environment_config(workspace.repo_path) or EnvironmentConfig()

        config.agent_budget.max_iterations = body.max_turns
        config.max_cost_usd = body.max_cost_usd
        config.agent_type_models = {
            entry.agent_type: entry.default_model for entry in body.agent_models
        }

        save_environment_config(workspace.repo_path, config)
        return _config_to_response(config)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to save settings", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )
