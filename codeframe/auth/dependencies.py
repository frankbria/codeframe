"""Authentication dependencies for route handlers."""
from fastapi import Depends
from codeframe.auth.models import User
from codeframe.auth.manager import current_active_user

async def get_current_user(user: User = Depends(current_active_user)) -> User:
    """Get currently authenticated user.
    
    Replacement for codeframe.ui.auth.get_current_user.
    Returns fastapi-users User model instead of Pydantic User.
    """
    return user
