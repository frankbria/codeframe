"""Session state persistence for continuous workflow."""

import json
import os
from datetime import datetime
from typing import Dict, Optional


class SessionManager:
    """Manages session state persistence between CLI restarts.

    Stores session context in .codeframe/session_state.json including:
    - Last session summary
    - Next actions queue
    - Current plan/task
    - Active blockers
    - Progress percentage
    """

    def __init__(self, project_path: str):
        """Initialize session manager.

        Args:
            project_path: Absolute path to project directory
        """
        self.project_path = project_path
        self.state_file = os.path.join(project_path, ".codeframe", "session_state.json")

    def save_session(self, state: Dict) -> None:
        """Save session state to file.

        Args:
            state: Session state dictionary containing:
                - summary (str): Summary of last session
                - completed_tasks (List[int]): Completed task IDs
                - next_actions (List[str]): Next action items
                - current_plan (str): Current task/plan
                - active_blockers (List[Dict]): Active blocker info
                - progress_pct (float): Progress percentage
        """
        session_data = {
            'last_session': {
                'summary': state.get('summary', 'No activity'),
                'completed_tasks': state.get('completed_tasks', []),
                'timestamp': datetime.now().isoformat()
            },
            'next_actions': state.get('next_actions', []),
            'current_plan': state.get('current_plan'),
            'active_blockers': state.get('active_blockers', []),
            'progress_pct': state.get('progress_pct', 0)
        }

        # Ensure .codeframe directory exists
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        # Write state file with restricted permissions
        try:
            with open(self.state_file, 'w') as f:
                json.dump(session_data, f, indent=2)

            # Set file permissions to user-only (0o600)
            os.chmod(self.state_file, 0o600)
        except IOError as e:
            print(f"Warning: Failed to save session state: {e}")

    def load_session(self) -> Optional[Dict]:
        """Load session state from file.

        Returns:
            Session state dictionary or None if no state exists
        """
        if not os.path.exists(self.state_file):
            return None

        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load session state: {e}")
            return None

    def clear_session(self) -> None:
        """Clear session state file."""
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except IOError as e:
                print(f"Warning: Failed to clear session state: {e}")
