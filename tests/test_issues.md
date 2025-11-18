# Issues discovered while testing the full codebase

## Warnings discovered in /blockers/

============================================================================================================================================================================================================== warnings summary ===============================================================================================================================================================================================================
codeframe/agents/test_worker_agent.py:25
  /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py:25: PytestCollectionWarning: cannot collect test class 'TestWorkerAgent' because it has a __init__ constructor (from: tests/blockers/test_blocker_answer_injection.py)
    class TestWorkerAgent(WorkerAgent):

codeframe/agents/test_worker_agent.py:25
  /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py:25: PytestCollectionWarning: cannot collect test class 'TestWorkerAgent' because it has a __init__ constructor (from: tests/blockers/test_blocker_type_validation.py)
    class TestWorkerAgent(WorkerAgent):

codeframe/agents/test_worker_agent.py:25
  /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py:25: PytestCollectionWarning: cannot collect test class 'TestWorkerAgent' because it has a __init__ constructor (from: tests/blockers/test_wait_for_blocker_resolution.py)
    class TestWorkerAgent(WorkerAgent):

tests/blockers/test_blockers.py::TestDuplicateResolution::test_concurrent_resolution_race_condition
  /home/frankbria/projects/codeframe/.venv/lib/python3.13/site-packages/_pytest/threadexception.py:58: PytestUnhandledThreadExceptionWarning: Exception in thread Thread-1 (resolve_a)
  
  Traceback (most recent call last):
    File "/home/frankbria/.local/share/uv/python/cpython-3.13.5-linux-x86_64-gnu/lib/python3.13/threading.py", line 1043, in _bootstrap_inner
      self.run()
      ~~~~~~~~^^
    File "/home/frankbria/.local/share/uv/python/cpython-3.13.5-linux-x86_64-gnu/lib/python3.13/threading.py", line 994, in run
      self._target(*self._args, **self._kwargs)
      ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/home/frankbria/projects/codeframe/tests/blockers/test_blockers.py", line 227, in resolve_a
      results.append(db.resolve_blocker(blocker_id, "Answer A"))
                     ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
    File "/home/frankbria/projects/codeframe/codeframe/persistence/database.py", line 749, in resolve_blocker
      cursor.execute(
      ~~~~~~~~~~~~~~^
          """UPDATE blockers
          ^^^^^^^^^^^^^^^^^^
      ...<2 lines>...
          (answer, resolved_at, blocker_id),
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      )
      ^
  sqlite3.InterfaceError: bad parameter or other API misuse
  
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
    warnings.warn(pytest.PytestUnhandledThreadExceptionWarning(msg))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

## Warnings discovered in /enforcement/

============================================================================================================================================================================================================== warnings summary ===============================================================================================================================================================================================================
codeframe/enforcement/adaptive_test_runner.py:62
  /home/frankbria/projects/codeframe/codeframe/enforcement/adaptive_test_runner.py:62: PytestCollectionWarning: cannot collect test class 'TestResult' because it has a __init__ constructor (from: tests/enforcement/test_adaptive_test_runner.py)
    @dataclass

codeframe/enforcement/adaptive_test_runner.py:62
  /home/frankbria/projects/codeframe/codeframe/enforcement/adaptive_test_runner.py:62: PytestCollectionWarning: cannot collect test class 'TestResult' because it has a __init__ constructor (from: tests/enforcement/test_evidence_verifier.py)
    @dataclass

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

## Warnings discovered in /notifiations/

========================================================================================================================================================================== warnings summary ==========================================================================================================================================================================
tests/notifications/test_webhook_notifications.py::TestWebhookNotificationService::test_send_blocker_notification_timeout
tests/notifications/test_webhook_notifications.py::TestWebhookNotificationService::test_send_blocker_notification_client_error
tests/notifications/test_webhook_notifications.py::TestWebhookNotificationService::test_send_blocker_notification_unexpected_error
tests/notifications/test_webhook_notifications.py::TestWebhookNotificationService::test_send_blocker_notification_http_error_status
  /home/frankbria/projects/codeframe/codeframe/notifications/webhook.py:133: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    async with session.post(
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

tests/notifications/test_webhook_notifications.py::TestWebhookNotificationService::test_send_blocker_notification_correct_payload
  /home/frankbria/.local/share/uv/python/cpython-3.13.5-linux-x86_64-gnu/lib/python3.13/contextlib.py:136: RuntimeWarning: coroutine 'WebhookNotificationService.send_blocker_notification' was never awaited
    def __enter__(self):
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

## Warnings discovered in /testing/

========================================================================================================================================================================== warnings summary ==========================================================================================================================================================================
codeframe/testing/models.py:12
  /home/frankbria/projects/codeframe/codeframe/testing/models.py:12: PytestCollectionWarning: cannot collect test class 'TestResult' because it has a __init__ constructor (from: tests/testing/test_self_correction_integration.py)
    @dataclass

codeframe/testing/models.py:12
  /home/frankbria/projects/codeframe/codeframe/testing/models.py:12: PytestCollectionWarning: cannot collect test class 'TestResult' because it has a __init__ constructor (from: tests/testing/test_test_runner.py)
    @dataclass

codeframe/testing/test_runner.py:19
  /home/frankbria/projects/codeframe/codeframe/testing/test_runner.py:19: PytestCollectionWarning: cannot collect test class 'TestRunner' because it has a __init__ constructor (from: tests/testing/test_test_runner.py)
    class TestRunner:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

## Warnings discovered in /agents/

========================================================================================================================================================================== warnings summary ==========================================================================================================================================================================
codeframe/agents/test_worker_agent.py:25
  /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py:25: PytestCollectionWarning: cannot collect test class 'TestWorkerAgent' because it has a __init__ constructor (from: tests/agents/test_agent_pool_manager.py)
    class TestWorkerAgent(WorkerAgent):

codeframe/agents/test_worker_agent.py:25
  /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py:25: PytestCollectionWarning: cannot collect test class 'TestWorkerAgent' because it has a __init__ constructor (from: tests/agents/test_test_worker_agent.py)
    class TestWorkerAgent(WorkerAgent):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html


## ***ERRORS discovered in /api/

====================================================================================================================================================================== short test summary info =======================================================================================================================================================================
SKIPPED [1] tests/api/test_project_creation_api.py:215: Database close() creates ungraceful crashes, not 500 errors. This test design is flawed.
FAILED tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_null_when_discovery_not_started - assert 404 == 200
FAILED tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_progress_when_discovering - assert 404 == 200
FAILED tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_100_percent_when_completed - assert 404 == 200
FAILED tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_matches_project_phase - assert 404 == 200
FAILED tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_excludes_answers_field - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatEndpoint::test_send_message_success - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatEndpoint::test_send_message_agent_not_started - assert 404 == 400
FAILED tests/api/test_chat_api.py::TestChatEndpoint::test_send_message_agent_failure - assert 404 == 500
FAILED tests/api/test_chat_api.py::TestChatHistoryEndpoint::test_get_history_success - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatHistoryEndpoint::test_get_history_pagination - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatHistoryEndpoint::test_get_history_empty - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatWebSocketIntegration::test_chat_broadcasts_message - assert 404 == 200
FAILED tests/api/test_chat_api.py::TestChatWebSocketIntegration::test_chat_continues_when_broadcast_fails - assert 404 == 200
FAILED tests/api/test_project_creation_api.py::TestProjectCreationAPI::test_create_project_duplicate_name - assert 500 == 201
FAILED tests/api/test_project_creation_api.py::TestProjectCreationAPI::test_create_project_returns_all_fields - assert 500 == 201
FAILED tests/api/test_project_creation_api.py::TestProjectCreationAPI::test_create_project_default_type - assert 500 == 201
FAILED tests/api/test_project_creation_api.py::TestProjectCreationIntegration::test_create_multiple_projects - assert 500 == 201
FAILED tests/api/test_project_creation_api.py::TestProjectCreationIntegration::test_create_project_via_api_then_get_status - assert 500 == 201

## Slow Tests and Causes

======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
192.09s call     tests/agents/test_lead_agent.py::TestLeadAgentErrorHandling::test_chat_handles_database_error
125.39s call     tests/agents/test_lead_agent.py::TestLeadAgentIntegration::test_complete_conversation_workflow
89.26s call     tests/agents/test_lead_agent.py::TestLeadAgentConversationPersistence::test_conversation_handles_long_history
88.50s call     tests/agents/test_lead_agent_blocker_handling.py::TestLeadAgentSyncBlockerHandling::test_sync_blocker_pauses_dependent_tasks
86.43s call     tests/agents/test_lead_agent.py::TestLeadAgentTokenUsageTracking::test_chat_tracks_total_tokens
76.04s setup    tests/agents/test_lead_agent_git_integration.py::TestLeadAgentGitWorkflowIntegration::test_workflow_with_no_tasks_fails
68.56s call     tests/agents/test_lead_agent.py::TestLeadAgentIntegration::test_agent_restart_maintains_context
64.17s call     tests/agents/test_lead_agent_blocker_handling.py::TestLeadAgentSyncBlockerHandling::test_sync_blocker_does_not_block_independent_tasks
62.12s call     tests/agents/test_lead_agent.py::TestLeadAgentTokenUsageTracking::test_chat_logs_token_usage
60.05s call     tests/agents/test_test_worker_agent.py::TestErrorHandling::test_handle_execution_timeout
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
192.17s setup    tests/git/test_git_auto_commit.py::TestCommitCreation::test_commit_single_file_change
116.47s setup    tests/git/test_git_auto_commit.py::TestCommitCreation::test_commit_message_in_git_log
86.06s setup    tests/git/test_git_auto_commit.py::TestCommitMessageGeneration::test_generate_message_without_description
79.81s setup    tests/git/test_git_auto_commit.py::TestCommitCreation::test_commit_returns_valid_sha
75.64s setup    tests/git/test_git_auto_commit.py::TestCommitMessageGeneration::test_infer_commit_type_from_keywords
67.06s setup    tests/git/test_git_auto_commit.py::TestCommitCreation::test_commit_on_feature_branch
65.47s setup    tests/git/test_git_workflow_manager.py::TestMergeToMain::test_merge_to_main_conflict_handling
61.56s setup    tests/git/test_git_workflow_manager.py::TestEdgeCases::test_empty_issue_number
58.62s setup    tests/git/test_git_workflow_manager.py::TestMergeToMain::test_merge_to_main_updates_database
54.82s setup    tests/git/test_git_auto_commit.py::TestCommitCreation::test_commit_multiple_files
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
214.32s call     tests/discovery/test_discovery_integration.py::TestDiscoveryDatabasePersistence::test_discovery_state_reloads_on_agent_restart
130.13s call     tests/discovery/test_discovery_integration.py::TestDiscoveryCompletionDetection::test_get_discovery_status_includes_structured_data
113.94s call     tests/discovery/test_discovery_integration.py::TestDiscoveryCompletionDetection::test_get_discovery_status_returns_completion_state
82.36s call     tests/discovery/test_discovery_integration.py::TestDiscoveryProgressIndicators::test_get_discovery_status_includes_progress_percentage_at_0_percent
81.63s call     tests/discovery/test_discovery_integration.py::TestDiscoveryAnswerProcessing::test_process_discovery_answer_updates_progress
74.36s call     tests/discovery/test_discovery_integration.py::TestDiscoveryProgressIndicators::test_get_discovery_status_includes_progress_percentage_at_100_percent
72.42s call     tests/discovery/test_discovery_integration.py::TestDiscoveryDatabasePersistence::test_discovery_answers_persist_in_database
65.32s call     tests/discovery/test_discovery_integration.py::TestDiscoveryFlowInitialization::test_discovery_state_persists_in_database
61.29s call     tests/discovery/test_discovery_integration.py::TestDiscoveryAnswerProcessing::test_process_discovery_answer_asks_next_question
59.34s call     tests/discovery/test_discovery_integration.py::TestDiscoveryStateTransitions::test_discovery_transitions_to_completed_when_all_required_answered
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
287.50s call     tests/integration/test_flash_save_workflow.py::TestFlashSaveWorkflow::test_flash_save_workflow_with_150_items
63.11s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_worker_saves_and_loads_context
44.63s setup    tests/integration/test_score_recalculation.py::TestScoreRecalculationIntegration::test_recalculation_with_multiple_items
36.62s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_tier_filtering_works
33.76s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_multiple_item_types
32.14s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_get_context_item_by_id
30.48s setup    tests/integration/test_worker_context_storage.py::TestMVPDemonstration::test_mvp_demo_agent_saves_task_and_retrieves
27.67s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_context_persists_across_sessions
22.37s setup    tests/integration/test_worker_context_storage.py::TestWorkerContextStorageIntegration::test_access_tracking_updates
21.90s setup    tests/integration/test_flash_save_workflow.py::TestFlashSaveWorkflow::test_flash_save_workflow_with_150_items
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
93.32s setup    tests/deployment/test_deployer.py::TestDeploymentEdgeCases::test_deployment_with_long_output
44.70s setup    tests/deployment/test_deployer.py::TestTriggerDeployment::test_trigger_deployment_measures_duration
37.26s setup    tests/deployment/test_deployer.py::TestDeployerInitialization::test_init_with_valid_paths
36.41s call     tests/deployment/test_deployer.py::TestDeploymentDatabaseTracking::test_deployment_graceful_without_deployments_table
36.16s setup    tests/deployment/test_deployer.py::TestDeploymentEdgeCases::test_deployment_with_empty_commit_hash
34.76s setup    tests/deployment/test_deployer.py::TestTriggerDeployment::test_trigger_deployment_default_environment
34.76s setup    tests/deployment/test_deployer.py::TestDeploymentEdgeCases::test_deployment_with_stderr_output
34.62s setup    tests/deployment/test_deployer.py::TestTriggerDeployment::test_trigger_deployment_returns_deployment_id
31.27s setup    tests/deployment/test_deployer.py::TestDeploymentDatabaseTracking::test_deployment_records_in_database_if_table_exists
26.72s setup    tests/deployment/test_deployer.py::TestTriggerDeployment::test_trigger_deployment_captures_output
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
185.92s setup    tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_404_for_nonexistent_project
83.96s setup    tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_null_when_discovery_not_started
64.37s setup    tests/api/test_chat_api.py::TestChatHistoryEndpoint::test_get_history_success
60.73s setup    tests/api/test_chat_api.py::TestChatEndpoint::test_send_message_agent_not_started
59.23s setup    tests/api/test_project_creation_api.py::TestProjectCreationAPI::test_create_project_success
56.98s setup    tests/api/test_blocker_resolution_api.py::TestBlockerResolveResponseStructure::test_resolve_response_has_required_fields
49.26s setup    tests/api/test_health_endpoint.py::test_health_endpoint_returns_json
43.97s setup    tests/api/test_chat_api.py::TestChatEndpoint::test_send_message_project_not_found
41.05s call     tests/api/test_api_discovery_progress.py::TestDiscoveryProgressEndpoint::test_get_discovery_progress_returns_100_percent_when_completed
39.81s setup    tests/api/test_chat_api.py::TestChatHistoryEndpoint::test_get_history_empty
======================================================================================================================================================================== slowest 10 durations ========================================================================================================================================================================
188.68s call     tests/persistence/test_database.py::TestDatabaseInitialization::test_database_initialization
136.85s call     tests/persistence/test_database_issues.py::TestIssueConstraints::test_unique_issue_number_per_project
111.54s call     tests/persistence/test_server_database.py::TestServerDatabaseIntegration::test_server_startup_with_database
109.64s call     tests/persistence/test_database.py::TestProjectCRUD::test_create_project
86.69s call     tests/persistence/test_database.py::TestProjectCRUD::test_get_nonexistent_project_returns_none
83.17s call     tests/persistence/test_database.py::TestProjectCRUD::test_get_project_by_id
82.68s call     tests/persistence/test_server_database.py::TestServerDatabaseInitialization::test_database_uses_config_path
76.85s call     tests/persistence/test_database_issues.py::TestIssueConstraints::test_issue_status_constraint
69.71s call     tests/persistence/test_database_issues.py::TestIssueConstraints::test_same_issue_number_different_projects_allowed
67.62s setup    tests/persistence/test_database_git_branches.py::TestGetAllBranchesForIssue::test_get_all_branches_for_issue_none


