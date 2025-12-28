# Test Mocking Audit Report

## Summary

- **Files Analyzed**: 148
- **Total Tests**: 2202
- **Total Mock Patterns**: 1081

### Severity Distribution

- **HIGH** (needs rewrite): 96
- **MEDIUM** (review needed): 98
- **LOW** (acceptable): 2008

---

## HIGH Severity Tests (Needs Rewrite)

These tests mock core functionality and should be rewritten as integration tests.

### `TestAgentLifecycleErrorHandling.test_start_agent_handles_database_error_gracefully`
- **File**: `/home/user/codeframe/tests/agents/test_agent_lifecycle.py:518`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.ui.server.app.state.db.get_project`** (patch, line 524): Mocking core functionality: database retrieval methods

### `TestThreeAgentParallelExecution.test_parallel_execution_three_agents`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:179`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 211): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task`** (patch, line 214): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.test_worker_agent.TestWorkerAgent.execute_task`** (patch, line 217): Mocking core functionality: task execution (core agent functionality)

### `TestDependencyBlocking.test_task_waits_for_dependency`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:267`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 311): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task`** (patch, line 315): Mocking core functionality: task execution (core agent functionality)

### `TestDependencyUnblocking.test_task_starts_when_unblocked`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:335`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 381): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task`** (patch, line 385): Mocking core functionality: task execution (core agent functionality)

### `TestComplexDependencyGraph.test_complex_dependency_graph_ten_tasks`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:404`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 474): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task`** (patch, line 477): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.test_worker_agent.TestWorkerAgent.execute_task`** (patch, line 480): Mocking core functionality: task execution (core agent functionality)

### `TestAgentReuse.test_agent_reuse_same_type_tasks`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:520`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 533): Mocking core functionality: task execution (core agent functionality)

### `TestErrorRecovery.test_task_retry_after_failure`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:562`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 583): Mocking core functionality: task execution (core agent functionality)

### `TestErrorRecovery.test_task_fails_after_max_retries`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:598`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 607): Mocking core functionality: task execution (core agent functionality)

### `TestCompletionDetection.test_completion_detection_all_tasks_done`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:627`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 633): Mocking core functionality: task execution (core agent functionality)

### `TestConcurrentDatabaseAccess.test_concurrent_task_updates_no_race_conditions`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:658`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 668): Mocking core functionality: task execution (core agent functionality)

### `TestWebSocketBroadcasts.test_websocket_broadcasts_all_events`
- **File**: `/home/user/codeframe/tests/agents/test_multi_agent_integration.py:697`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `unspecified` (Mock, line 700): Direct Mock object creation
  - **`codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task`** (patch, line 712): Mocking core functionality: task execution (core agent functionality)
  - **`codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task`** (patch, line 715): Mocking core functionality: task execution (core agent functionality)

### `TestServeBasicFunctionality.test_serve_default_port`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:18`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 16): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 17): Potentially excessive mock: codeframe.cli.check_port_availability
  - `unspecified` (Mock, line 25): Direct Mock object creation

### `TestServeBasicFunctionality.test_serve_keyboard_interrupt`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:40`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 38): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 39): Potentially excessive mock: codeframe.cli.check_port_availability

### `TestServeCustomPort.test_serve_custom_port`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:63`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 61): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 62): Potentially excessive mock: codeframe.cli.check_port_availability
  - `unspecified` (Mock, line 69): Direct Mock object creation

### `TestServeCustomPort.test_serve_port_in_use`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:92`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 90): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 91): Potentially excessive mock: codeframe.cli.check_port_availability

### `TestServeCustomPort.test_serve_subprocess_failure`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:109`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 107): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 108): Potentially excessive mock: codeframe.cli.check_port_availability

### `TestServeBrowserOpening.test_serve_browser_opens`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:135`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `codeframe.cli.threading.Thread` (patch, line 132): Potentially excessive mock: codeframe.cli.threading.Thread
  - **`codeframe.cli.subprocess.run`** (patch, line 133): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 134): Potentially excessive mock: codeframe.cli.check_port_availability
  - `unspecified` (Mock, line 141): Direct Mock object creation
  - `unspecified` (Mock, line 142): Direct Mock object creation

### `TestServeBrowserOpening.test_serve_no_browser`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:156`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `codeframe.cli.threading.Thread` (patch, line 153): Potentially excessive mock: codeframe.cli.threading.Thread
  - **`codeframe.cli.subprocess.run`** (patch, line 154): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 155): Potentially excessive mock: codeframe.cli.check_port_availability
  - `unspecified` (Mock, line 162): Direct Mock object creation

### `TestServeReloadFlag.test_serve_reload_flag`
- **File**: `/home/user/codeframe/tests/cli/test_serve_command.py:176`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.cli.subprocess.run`** (patch, line 174): Mocking core functionality: quality gate subprocess execution
  - `codeframe.cli.check_port_availability` (patch, line 175): Potentially excessive mock: codeframe.cli.check_port_availability
  - `unspecified` (Mock, line 182): Direct Mock object creation

### `TestAdaptiveTestRunner.test_detects_language_on_first_run`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:18`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 26): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 27): Direct Mock object creation

### `TestAdaptiveTestRunner.test_parses_pytest_output`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:35`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 41): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 42): Direct Mock object creation

### `TestAdaptiveTestRunner.test_parses_jest_output`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:56`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 63): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 64): Direct Mock object creation

### `TestAdaptiveTestRunner.test_parses_go_test_output`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:75`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 81): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 82): Direct Mock object creation

### `TestAdaptiveTestRunner.test_parses_rust_cargo_output`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:99`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 105): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 106): Direct Mock object creation

### `TestAdaptiveTestRunner.test_extracts_coverage_from_pytest`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:119`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 125): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 126): Direct Mock object creation

### `TestAdaptiveTestRunner.test_extracts_coverage_from_jest`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:140`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 147): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 148): Direct Mock object creation

### `TestAdaptiveTestRunner.test_handles_test_failures`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:162`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 168): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 169): Direct Mock object creation

### `TestAdaptiveTestRunner.test_detects_skipped_tests`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:179`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 185): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 186): Direct Mock object creation

### `TestAdaptiveTestRunner.test_calculates_pass_rate`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:195`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 201): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 202): Direct Mock object creation

### `TestAdaptiveTestRunner.test_handles_subprocess_errors`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:211`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 217): Mocking core functionality: quality gate subprocess execution

### `TestAdaptiveTestRunnerOutputParsing.test_parses_maven_output`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:229`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 235): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 236): Direct Mock object creation

### `TestAdaptiveTestRunnerOutputParsing.test_handles_no_tests_found`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:247`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 253): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 254): Direct Mock object creation

### `TestAdaptiveTestRunnerOutputParsing.test_combines_stdout_and_stderr`
- **File**: `/home/user/codeframe/tests/enforcement/test_adaptive_test_runner.py:265`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.enforcement.adaptive_test_runner.subprocess.run`** (patch, line 271): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 272): Direct Mock object creation

### `TestQualityGatesIntegration.test_quality_gate_workflow_all_pass`
- **File**: `/home/user/codeframe/tests/integration/test_quality_gates_integration.py:121`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 141): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 147): Direct Mock object creation
  - `unspecified` (Mock, line 154): Direct Mock object creation
  - `unspecified` (Mock, line 157): Direct Mock object creation
  - `unspecified` (Mock, line 158): Direct Mock object creation
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 163): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 165): Direct Mock object creation
  - `unspecified` (AsyncMock, line 168): Direct Mock object creation

### `TestQualityGatesIntegration.test_quality_gate_workflow_test_failure`
- **File**: `/home/user/codeframe/tests/integration/test_quality_gates_integration.py:193`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 213): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 214): Direct Mock object creation

### `TestQualityGatesIntegration.test_quality_gate_workflow_low_coverage`
- **File**: `/home/user/codeframe/tests/integration/test_quality_gates_integration.py:308`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 327): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 328): Direct Mock object creation

### `TestQualityGatesIntegration.test_skip_detection_in_run_all_gates`
- **File**: `/home/user/codeframe/tests/integration/test_quality_gates_integration.py:383`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 417): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 418): Direct Mock object creation
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 424): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 426): Direct Mock object creation
  - `unspecified` (AsyncMock, line 429): Direct Mock object creation
  - `codeframe.lib.quality_gates.SkipPatternDetector` (patch, line 431): Potentially excessive mock: codeframe.lib.quality_gates.SkipPatternDetector

### `TestQualityMetricsRecording.test_metrics_recorded_after_quality_gates_pass`
- **File**: `/home/user/codeframe/tests/integration/test_quality_tracker_integration.py:115`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.lib.quality_gates.QualityGates.run_all_gates`** (patch, line 132): Mocking core functionality: quality gate methods
  - `unspecified` (Mock, line 139): Direct Mock object creation

### `TestQualityDegradationDetection.test_blocker_created_on_degradation`
- **File**: `/home/user/codeframe/tests/integration/test_quality_tracker_integration.py:177`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`codeframe.lib.quality_gates.QualityGates.run_all_gates`** (patch, line 198): Mocking core functionality: quality gate methods
  - `unspecified` (Mock, line 207): Direct Mock object creation

### `TestQualityGates.test_block_on_test_failure`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:91`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 105): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 106): Direct Mock object creation

### `TestQualityGates.test_block_on_type_errors`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:127`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 142): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 143): Direct Mock object creation

### `TestQualityGates.test_block_on_low_coverage`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:164`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 167): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 168): Direct Mock object creation

### `TestQualityGates.test_pass_all_gates`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:222`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 248): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 255): Direct Mock object creation
  - `unspecified` (Mock, line 259): Direct Mock object creation
  - `unspecified` (Mock, line 261): Direct Mock object creation
  - `unspecified` (Mock, line 263): Direct Mock object creation
  - `unspecified` (Mock, line 264): Direct Mock object creation
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 269): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 271): Direct Mock object creation
  - `unspecified` (AsyncMock, line 274): Direct Mock object creation

### `TestQualityGates.test_create_blocker_on_failure`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:287`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 290): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 291): Direct Mock object creation

### `TestQualityGates.test_linting_gate`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:351`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 366): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 367): Direct Mock object creation

### `TestQualityGatesErrorHandling.test_jest_failure`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:500`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 506): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 507): Direct Mock object creation

### `TestQualityGatesErrorHandling.test_tsc_failure`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:526`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 532): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 533): Direct Mock object creation

### `TestQualityGatesErrorHandling.test_eslint_failure`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:552`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 558): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 559): Direct Mock object creation

### `TestQualityGatesErrorHandling.test_pytest_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:618`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 622): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_pytest_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:633`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 637): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_jest_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:646`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 650): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_jest_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:661`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 665): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_mypy_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:674`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 678): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_mypy_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:689`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 693): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_tsc_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:702`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 706): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_tsc_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:717`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 721): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_coverage_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:730`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 732): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_coverage_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:746`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 748): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_ruff_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:757`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 761): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_ruff_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:772`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 776): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_eslint_timeout`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:785`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 789): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesErrorHandling.test_eslint_not_found`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:800`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 804): Mocking core functionality: quality gate subprocess execution

### `TestQualityGatesIntegration.test_multiple_gate_failures`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:931`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 934): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 936): Direct Mock object creation
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 943): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 945): Direct Mock object creation
  - `unspecified` (Mock, line 948): Direct Mock object creation
  - `unspecified` (AsyncMock, line 958): Direct Mock object creation

### `TestQualityGatesIntegration.test_risky_file_patterns`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:967`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 995): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 996): Direct Mock object creation
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 998): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 1000): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1003): Direct Mock object creation

### `TestMacOSNotification.test_uses_fallback_when_pync_unavailable`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:59`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 57): Potentially excessive mock: platform.system
  - `codeframe.notifications.desktop.pync` (patch, line 58): Potentially excessive mock: codeframe.notifications.desktop.pync
  - **`subprocess.run`** (patch, line 61): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 62): Direct Mock object creation

### `TestMacOSFallback.test_sends_notification_with_osascript`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:76`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 73): Potentially excessive mock: platform.system
  - `codeframe.notifications.desktop.pync` (patch, line 74): Potentially excessive mock: codeframe.notifications.desktop.pync
  - **`subprocess.run`** (patch, line 75): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 78): Direct Mock object creation

### `TestLinuxNotification.test_sends_notification_with_notify_send`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:94`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 92): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 93): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 96): Direct Mock object creation

### `TestLinuxFallback.test_uses_dbus_when_notify_send_fails`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:113`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 111): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 112): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 117): Direct Mock object creation
  - `unspecified` (Mock, line 118): Direct Mock object creation

### `TestNotificationFormatting.test_truncates_long_title`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:167`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 165): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 166): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 169): Direct Mock object creation

### `TestNotificationFormatting.test_truncates_long_message`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:182`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 180): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 181): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 184): Direct Mock object creation

### `TestNotificationFormatting.test_handles_empty_strings`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:197`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 195): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 196): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 199): Direct Mock object creation

### `TestFireAndForget.test_does_not_block_on_error`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:241`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 239): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 240): Mocking core functionality: quality gate subprocess execution

### `TestFireAndForget.test_logs_error_on_failure`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:251`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - `platform.system` (patch, line 249): Potentially excessive mock: platform.system
  - **`subprocess.run`** (patch, line 250): Mocking core functionality: quality gate subprocess execution
  - `codeframe.notifications.desktop.logger` (patch, line 256): Potentially excessive mock: codeframe.notifications.desktop.logger

### `TestTestRunnerExecution.test_run_tests_all_pass`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:99`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 109): Mocking core functionality: quality gate subprocess execution
  - `builtins.open` (patch, line 109): Potentially excessive mock: builtins.open
  - `unspecified` (MagicMock, line 110): Direct Mock object creation

### `TestTestRunnerExecution.test_run_tests_some_fail`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:123`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 133): Mocking core functionality: quality gate subprocess execution
  - `builtins.open` (patch, line 133): Potentially excessive mock: builtins.open
  - `unspecified` (MagicMock, line 134): Direct Mock object creation

### `TestTestRunnerExecution.test_run_tests_with_errors`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:146`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 155): Mocking core functionality: quality gate subprocess execution
  - `builtins.open` (patch, line 155): Potentially excessive mock: builtins.open
  - `unspecified` (MagicMock, line 156): Direct Mock object creation

### `TestTestRunnerExecution.test_run_tests_no_tests_found`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:167`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 176): Mocking core functionality: quality gate subprocess execution
  - `builtins.open` (patch, line 176): Potentially excessive mock: builtins.open
  - `unspecified` (MagicMock, line 177): Direct Mock object creation

### `TestTestRunnerExecution.test_run_tests_timeout`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:189`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 193): Mocking core functionality: quality gate subprocess execution

### `TestTestRunnerExecution.test_run_tests_pytest_not_installed`
- **File**: `/home/user/codeframe/tests/testing/test_test_runner.py:212`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 216): Mocking core functionality: quality gate subprocess execution

### `test_init_empty_git_called_process_error`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:90`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 89): Mocking core functionality: quality gate subprocess execution

### `test_init_empty_git_timeout`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:105`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 104): Mocking core functionality: quality gate subprocess execution

### `test_init_empty_git_not_found`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:114`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 113): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_success`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:126`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 125): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 128): Direct Mock object creation

### `test_init_from_git_network_error`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:165`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 164): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_repository_not_found`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:180`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 179): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_branch_not_found_specific`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:195`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 194): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_branch_pattern_match`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:221`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 220): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_authentication_failed`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:243`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 242): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_permission_denied`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:258`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 257): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_generic_error`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:273`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 272): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_timeout_expired`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:288`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 287): Mocking core functionality: quality gate subprocess execution

### `test_init_from_git_file_not_found`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:301`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 300): Mocking core functionality: quality gate subprocess execution

### `test_init_from_local_git_init_fails_gracefully`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:424`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 423): Mocking core functionality: quality gate subprocess execution

### `test_init_from_upload_placeholder`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:497`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 496): Mocking core functionality: quality gate subprocess execution
  - `unspecified` (Mock, line 499): Direct Mock object creation

### `test_create_workspace_cleanup_on_failure`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:513`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 512): Mocking core functionality: quality gate subprocess execution

### `test_git_clone_with_stderr_none`
- **File**: `/home/user/codeframe/tests/workspace/test_workspace_manager_comprehensive.py:562`
- **Recommendation**: Rewrite as integration test with real implementations
- **Mock Patterns**:
  - **`subprocess.run`** (patch, line 561): Mocking core functionality: quality gate subprocess execution

## MEDIUM Severity Tests (Review Needed)

These tests have heavy mocking that may hide integration issues.

### `TestAgentLifecycleIntegration.test_complete_start_workflow_end_to_end`
- **File**: `/home/user/codeframe/tests/agents/test_agent_lifecycle.py:391`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.ui.shared.LeadAgent` (patch, line 421): Potentially excessive mock: codeframe.ui.shared.LeadAgent
  - `codeframe.ui.shared.manager.broadcast` (patch, line 422): Potentially excessive mock: codeframe.ui.shared.manager.broadcast
  - `unspecified` (Mock, line 424): Direct Mock object creation

### `TestRunningAgentsDictionary.test_running_agents_dictionary_handles_multiple_projects`
- **File**: `/home/user/codeframe/tests/agents/test_agent_lifecycle.py:478`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 487): Direct Mock object creation
  - `unspecified` (Mock, line 488): Direct Mock object creation
  - `unspecified` (Mock, line 489): Direct Mock object creation

### `TestHybridAgentCreation.test_create_hybrid_agent_when_use_sdk_true`
- **File**: `/home/user/codeframe/tests/agents/test_agent_pool_manager.py:334`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.agent_pool_manager.SDK_AVAILABLE` (patch, line 331): Potentially excessive mock: codeframe.agents.agent_pool_manager.SDK_AVAILABLE
  - `codeframe.agents.agent_pool_manager.SDKClientWrapper` (patch, line 332): Potentially excessive mock: codeframe.agents.agent_pool_manager.SDKClientWrapper
  - `codeframe.agents.agent_pool_manager.HybridWorkerAgent` (patch, line 333): Potentially excessive mock: codeframe.agents.agent_pool_manager.HybridWorkerAgent
  - `unspecified` (Mock, line 338): Direct Mock object creation
  - `unspecified` (Mock, line 339): Direct Mock object creation

### `TestHybridAgentCreation.test_create_agent_with_use_sdk_override`
- **File**: `/home/user/codeframe/tests/agents/test_agent_pool_manager.py:376`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.agent_pool_manager.SDK_AVAILABLE` (patch, line 373): Potentially excessive mock: codeframe.agents.agent_pool_manager.SDK_AVAILABLE
  - `codeframe.agents.agent_pool_manager.SDKClientWrapper` (patch, line 374): Potentially excessive mock: codeframe.agents.agent_pool_manager.SDKClientWrapper
  - `codeframe.agents.agent_pool_manager.HybridWorkerAgent` (patch, line 375): Potentially excessive mock: codeframe.agents.agent_pool_manager.HybridWorkerAgent
  - `unspecified` (Mock, line 380): Direct Mock object creation
  - `unspecified` (Mock, line 381): Direct Mock object creation

### `TestBackendWorkerAgentCodeGeneration.test_generate_code_creates_single_file`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:614`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 612): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 616): Direct Mock object creation
  - `unspecified` (Mock, line 617): Direct Mock object creation
  - `unspecified` (AsyncMock, line 620): Direct Mock object creation
  - `unspecified` (Mock, line 623): Direct Mock object creation
  - `unspecified` (Mock, line 625): Direct Mock object creation

### `TestBackendWorkerAgentCodeGeneration.test_generate_code_modifies_multiple_files`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:669`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 667): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 671): Direct Mock object creation
  - `unspecified` (Mock, line 672): Direct Mock object creation
  - `unspecified` (AsyncMock, line 674): Direct Mock object creation
  - `unspecified` (Mock, line 677): Direct Mock object creation
  - `unspecified` (Mock, line 679): Direct Mock object creation

### `TestBackendWorkerAgentCodeGeneration.test_generate_code_handles_api_error`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:724`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 722): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 726): Direct Mock object creation
  - `unspecified` (Mock, line 727): Direct Mock object creation
  - `unspecified` (AsyncMock, line 729): Direct Mock object creation

### `TestBackendWorkerAgentCodeGeneration.test_generate_code_handles_malformed_response`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:757`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 755): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 759): Direct Mock object creation
  - `unspecified` (Mock, line 760): Direct Mock object creation
  - `unspecified` (AsyncMock, line 762): Direct Mock object creation
  - `unspecified` (Mock, line 765): Direct Mock object creation
  - `unspecified` (Mock, line 766): Direct Mock object creation

### `TestBackendWorkerAgentExecution.test_execute_task_success`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:1132`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 1130): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 1165): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1169): Direct Mock object creation
  - `unspecified` (Mock, line 1171): Direct Mock object creation
  - `unspecified` (Mock, line 1173): Direct Mock object creation

### `TestBackendWorkerAgentExecution.test_execute_task_handles_file_operation_failure`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:1293`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 1291): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 1325): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1329): Direct Mock object creation
  - `unspecified` (Mock, line 1331): Direct Mock object creation
  - `unspecified` (Mock, line 1333): Direct Mock object creation

### `TestBackendWorkerAgentTestRunnerIntegration.test_execute_task_runs_tests_after_code_generation`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:1381`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 1379): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 1416): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1420): Direct Mock object creation
  - `unspecified` (Mock, line 1422): Direct Mock object creation
  - `unspecified` (Mock, line 1424): Direct Mock object creation

### `TestBackendWorkerAgentTestRunnerIntegration.test_execute_task_handles_test_failures`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:1479`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 1477): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 1512): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1516): Direct Mock object creation
  - `unspecified` (Mock, line 1518): Direct Mock object creation
  - `unspecified` (Mock, line 1520): Direct Mock object creation
  - `unspecified` (Mock, line 1560): Direct Mock object creation
  - `unspecified` (Mock, line 1562): Direct Mock object creation

### `TestBackendWorkerAgentTestRunnerIntegration.test_execute_task_handles_test_runner_errors`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_agent.py:1610`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 1608): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 1643): Direct Mock object creation
  - `unspecified` (AsyncMock, line 1647): Direct Mock object creation
  - `unspecified` (Mock, line 1649): Direct Mock object creation
  - `unspecified` (Mock, line 1651): Direct Mock object creation
  - `unspecified` (Mock, line 1693): Direct Mock object creation
  - `unspecified` (Mock, line 1695): Direct Mock object creation

### `test_backend_worker_commits_after_successful_task`
- **File**: `/home/user/codeframe/tests/agents/test_backend_worker_auto_commit.py:53`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 86): Direct Mock object creation
  - `unspecified` (Mock, line 89): Direct Mock object creation
  - `unspecified` (Mock, line 90): Direct Mock object creation

### `TestComponentGeneration.test_generate_component_with_api_success`
- **File**: `/home/user/codeframe/tests/agents/test_frontend_worker_agent.py:150`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.frontend_worker_agent.AsyncAnthropic` (patch, line 148): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 153): Direct Mock object creation
  - `unspecified` (Mock, line 157): Direct Mock object creation
  - `unspecified` (Mock, line 169): Direct Mock object creation

### `TestTokenTracking.test_records_token_usage`
- **File**: `/home/user/codeframe/tests/agents/test_hybrid_worker.py:269`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.metrics_tracker.MetricsTracker` (patch, line 271): Potentially excessive mock: codeframe.lib.metrics_tracker.MetricsTracker
  - `unspecified` (MagicMock, line 272): Direct Mock object creation
  - `unspecified` (AsyncMock, line 273): Direct Mock object creation

### `TestTokenTracking.test_token_tracking_failure_doesnt_break_execution`
- **File**: `/home/user/codeframe/tests/agents/test_hybrid_worker.py:286`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.metrics_tracker.MetricsTracker` (patch, line 288): Potentially excessive mock: codeframe.lib.metrics_tracker.MetricsTracker
  - `unspecified` (MagicMock, line 289): Direct Mock object creation
  - `unspecified` (AsyncMock, line 290): Direct Mock object creation

### `TestIntegration.test_full_execution_flow`
- **File**: `/home/user/codeframe/tests/agents/test_hybrid_worker.py:518`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.metrics_tracker.MetricsTracker` (patch, line 534): Potentially excessive mock: codeframe.lib.metrics_tracker.MetricsTracker
  - `unspecified` (MagicMock, line 535): Direct Mock object creation
  - `unspecified` (AsyncMock, line 536): Direct Mock object creation
  - `codeframe.lib.context_manager.ContextManager` (patch, line 539): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (MagicMock, line 540): Direct Mock object creation

### `TestLeadAgentTaskAssignment.test_t9_websocket_broadcast_called_when_present`
- **File**: `/home/user/codeframe/tests/agents/test_lead_agent.py:833`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 868): Direct Mock object creation
  - `codeframe.agents.lead_agent.AgentPoolManager` (patch, line 871): Potentially excessive mock: codeframe.agents.lead_agent.AgentPoolManager
  - `codeframe.ui.websocket_broadcasts.broadcast_task_assigned` (patch, line 872): Potentially excessive mock: codeframe.ui.websocket_broadcasts.broadcast_task_assigned
  - `asyncio.get_running_loop` (patch, line 873): Potentially excessive mock: asyncio.get_running_loop
  - `unspecified` (Mock, line 875): Direct Mock object creation
  - `unspecified` (Mock, line 878): Direct Mock object creation

### `TestTestGeneration.test_generate_tests_with_api_success`
- **File**: `/home/user/codeframe/tests/agents/test_test_worker_agent.py:169`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 167): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 171): Direct Mock object creation
  - `unspecified` (Mock, line 174): Direct Mock object creation
  - `unspecified` (Mock, line 186): Direct Mock object creation

### `TestSelfCorrection.test_correct_failing_tests`
- **File**: `/home/user/codeframe/tests/agents/test_test_worker_agent.py:286`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 284): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 288): Direct Mock object creation
  - `unspecified` (Mock, line 291): Direct Mock object creation
  - `unspecified` (Mock, line 298): Direct Mock object creation

### `TestWorkerAgentExecuteTask.test_execute_task_calls_token_tracking`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:291`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 331): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 333): Direct Mock object creation
  - `unspecified` (Mock, line 334): Direct Mock object creation
  - `unspecified` (AsyncMock, line 337): Direct Mock object creation

### `TestWorkerAgentExecuteTask.test_execute_task_sets_current_task`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:350`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 390): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 392): Direct Mock object creation
  - `unspecified` (Mock, line 393): Direct Mock object creation
  - `unspecified` (AsyncMock, line 396): Direct Mock object creation

### `TestWorkerAgentSecurityAndReliability.test_api_key_validation_accepts_valid_format`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:454`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 494): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 496): Direct Mock object creation
  - `unspecified` (Mock, line 497): Direct Mock object creation
  - `unspecified` (AsyncMock, line 500): Direct Mock object creation

### `TestWorkerAgentSecurityAndReliability.test_rate_limiting_prevents_excessive_calls`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:507`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 547): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 549): Direct Mock object creation
  - `unspecified` (Mock, line 550): Direct Mock object creation
  - `unspecified` (AsyncMock, line 553): Direct Mock object creation

### `TestWorkerAgentSecurityAndReliability.test_input_sanitization_prevents_prompt_injection`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:619`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 661): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 663): Direct Mock object creation
  - `unspecified` (Mock, line 664): Direct Mock object creation
  - `unspecified` (AsyncMock, line 667): Direct Mock object creation
  - `codeframe.agents.worker_agent.logger` (patch, line 670): Potentially excessive mock: codeframe.agents.worker_agent.logger

### `TestWorkerAgentSecurityAndReliability.test_retry_logic_handles_transient_failures`
- **File**: `/home/user/codeframe/tests/agents/test_worker_agent.py:684`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 723): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 728): Direct Mock object creation
  - `unspecified` (Mock, line 732): Direct Mock object creation
  - `unspecified` (Mock, line 733): Direct Mock object creation
  - `unspecified` (AsyncMock, line 737): Direct Mock object creation
  - `unspecified` (Mock, line 739): Direct Mock object creation
  - `unspecified` (Mock, line 740): Direct Mock object creation

### `TestBackendWorkerAgentAnswerInjection.test_create_blocker_and_wait_enriches_context_with_answer`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_answer_injection.py:29`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 32): Direct Mock object creation
  - `unspecified` (Mock, line 33): Direct Mock object creation
  - `unspecified` (Mock, line 39): Direct Mock object creation

### `TestBackendWorkerAgentAnswerInjection.test_create_blocker_and_wait_extracts_task_id_from_context`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_answer_injection.py:86`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 89): Direct Mock object creation
  - `unspecified` (Mock, line 90): Direct Mock object creation
  - `unspecified` (Mock, line 96): Direct Mock object creation

### `TestBackendWorkerAgentAnswerInjection.test_create_blocker_and_wait_uses_custom_timeouts`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_answer_injection.py:129`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 132): Direct Mock object creation
  - `unspecified` (Mock, line 133): Direct Mock object creation
  - `unspecified` (Mock, line 139): Direct Mock object creation

### `TestBackendWorkerAgentBlockerTypeValidation.test_create_blocker_accepts_sync_type`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_type_validation.py:28`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 30): Direct Mock object creation
  - `unspecified` (Mock, line 32): Direct Mock object creation
  - `unspecified` (Mock, line 38): Direct Mock object creation
  - `unspecified` (Mock, line 41): Direct Mock object creation

### `TestBackendWorkerAgentBlockerTypeValidation.test_create_blocker_accepts_async_type`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_type_validation.py:53`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 55): Direct Mock object creation
  - `unspecified` (Mock, line 57): Direct Mock object creation
  - `unspecified` (Mock, line 63): Direct Mock object creation

### `TestBackendWorkerAgentBlockerTypeValidation.test_create_blocker_defaults_to_async`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_type_validation.py:75`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 77): Direct Mock object creation
  - `unspecified` (Mock, line 79): Direct Mock object creation
  - `unspecified` (Mock, line 85): Direct Mock object creation

### `TestBackendWorkerAgentBlockerTypeValidation.test_create_blocker_rejects_invalid_type`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_type_validation.py:97`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 99): Direct Mock object creation
  - `unspecified` (Mock, line 100): Direct Mock object creation
  - `unspecified` (Mock, line 106): Direct Mock object creation

### `TestBackendWorkerAgentBlockerTypeValidation.test_create_blocker_rejects_lowercase_type`
- **File**: `/home/user/codeframe/tests/blockers/test_blocker_type_validation.py:119`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 121): Direct Mock object creation
  - `unspecified` (Mock, line 122): Direct Mock object creation
  - `unspecified` (Mock, line 128): Direct Mock object creation

### `TestBackendWorkerAgentBlockerResolution.test_wait_for_blocker_resolution_returns_answer_when_resolved`
- **File**: `/home/user/codeframe/tests/blockers/test_wait_for_blocker_resolution.py:29`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 32): Direct Mock object creation
  - `unspecified` (Mock, line 33): Direct Mock object creation
  - `unspecified` (Mock, line 39): Direct Mock object creation

### `TestBackendWorkerAgentBlockerResolution.test_wait_for_blocker_resolution_raises_timeout_when_not_resolved`
- **File**: `/home/user/codeframe/tests/blockers/test_wait_for_blocker_resolution.py:75`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 78): Direct Mock object creation
  - `unspecified` (Mock, line 79): Direct Mock object creation
  - `unspecified` (Mock, line 85): Direct Mock object creation

### `TestBackendWorkerAgentBlockerResolution.test_wait_for_blocker_resolution_polls_at_specified_interval`
- **File**: `/home/user/codeframe/tests/blockers/test_wait_for_blocker_resolution.py:111`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 114): Direct Mock object creation
  - `unspecified` (Mock, line 115): Direct Mock object creation
  - `unspecified` (Mock, line 121): Direct Mock object creation

### `TestBackendWorkerAgentBlockerResolution.test_wait_for_blocker_resolution_returns_immediately_if_already_resolved`
- **File**: `/home/user/codeframe/tests/blockers/test_wait_for_blocker_resolution.py:168`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 173): Direct Mock object creation
  - `unspecified` (Mock, line 174): Direct Mock object creation
  - `unspecified` (Mock, line 180): Direct Mock object creation

### `TestBackendWorkerAgentBlockerResolution.test_wait_for_blocker_resolution_broadcasts_agent_resumed_event`
- **File**: `/home/user/codeframe/tests/blockers/test_wait_for_blocker_resolution.py:211`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 214): Direct Mock object creation
  - `unspecified` (Mock, line 215): Direct Mock object creation
  - `unspecified` (AsyncMock, line 216): Direct Mock object creation
  - `unspecified` (Mock, line 228): Direct Mock object creation
  - `codeframe.ui.websocket_broadcasts.broadcast_agent_resumed` (patch, line 248): Potentially excessive mock: codeframe.ui.websocket_broadcasts.broadcast_agent_resumed

### `TestIsPortAvailable.test_port_unavailable`
- **File**: `/home/user/codeframe/tests/core/test_port_utils.py:23`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `socket.socket` (patch, line 22): Potentially excessive mock: socket.socket
  - `unspecified` (Mock, line 26): Direct Mock object creation
  - `unspecified` (Mock, line 27): Direct Mock object creation
  - `unspecified` (Mock, line 28): Direct Mock object creation

### `TestCheckPortAvailability.test_port_in_use_returns_helpful_message`
- **File**: `/home/user/codeframe/tests/core/test_port_utils.py:55`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `socket.socket` (patch, line 54): Potentially excessive mock: socket.socket
  - `unspecified` (Mock, line 58): Direct Mock object creation
  - `unspecified` (Mock, line 59): Direct Mock object creation
  - `unspecified` (Mock, line 60): Direct Mock object creation

### `TestCheckPortAvailability.test_other_os_error_returns_error_message`
- **File**: `/home/user/codeframe/tests/core/test_port_utils.py:74`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `socket.socket` (patch, line 73): Potentially excessive mock: socket.socket
  - `unspecified` (Mock, line 77): Direct Mock object creation
  - `unspecified` (Mock, line 78): Direct Mock object creation
  - `unspecified` (Mock, line 79): Direct Mock object creation

### `TestProjectPauseSuccessPath.test_pause_with_no_active_agents`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:83`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 81): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 82): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 88): Direct Mock object creation
  - `unspecified` (Mock, line 91): Direct Mock object creation
  - `unspecified` (Mock, line 92): Direct Mock object creation

### `TestProjectPauseSuccessPath.test_pause_with_flash_save_success`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:129`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 127): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 128): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 134): Direct Mock object creation
  - `unspecified` (Mock, line 144): Direct Mock object creation
  - `unspecified` (Mock, line 145): Direct Mock object creation

### `TestProjectPauseSuccessPath.test_pause_with_flash_save_failures_continues`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:173`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 171): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 172): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 178): Direct Mock object creation
  - `unspecified` (Mock, line 193): Direct Mock object creation
  - `unspecified` (Mock, line 194): Direct Mock object creation

### `TestProjectPauseSuccessPath.test_pause_with_reason_included_in_checkpoint`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:218`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 216): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 217): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 223): Direct Mock object creation
  - `unspecified` (Mock, line 225): Direct Mock object creation
  - `unspecified` (Mock, line 226): Direct Mock object creation

### `TestProjectPauseSuccessPath.test_pause_timestamp_consistency`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:245`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 243): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 244): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 250): Direct Mock object creation
  - `unspecified` (Mock, line 252): Direct Mock object creation
  - `unspecified` (Mock, line 253): Direct Mock object creation

### `TestProjectPauseErrorHandling.test_pause_rollback_on_checkpoint_failure`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:285`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 283): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 284): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 290): Direct Mock object creation
  - `unspecified` (Mock, line 292): Direct Mock object creation

### `TestProjectPauseErrorHandling.test_pause_handles_rollback_failure_gracefully`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:314`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 312): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 313): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 319): Direct Mock object creation
  - `unspecified` (Mock, line 321): Direct Mock object creation

### `TestProjectResumeWithPausedAt.test_resume_clears_paused_at_timestamp`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:340`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 339): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `unspecified` (Mock, line 345): Direct Mock object creation
  - `unspecified` (Mock, line 348): Direct Mock object creation
  - `unspecified` (Mock, line 365): Direct Mock object creation

### `TestProjectResumeWithPausedAt.test_resume_from_specific_checkpoint`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:378`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 377): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `unspecified` (Mock, line 383): Direct Mock object creation
  - `unspecified` (Mock, line 385): Direct Mock object creation
  - `unspecified` (Mock, line 397): Direct Mock object creation

### `TestProjectResumeWithPausedAt.test_resume_raises_error_when_checkpoint_not_found`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:423`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 422): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `unspecified` (Mock, line 427): Direct Mock object creation
  - `unspecified` (Mock, line 430): Direct Mock object creation

### `TestProjectPauseIdempotency.test_pause_when_already_paused`
- **File**: `/home/user/codeframe/tests/core/test_project_pause.py:441`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.checkpoint_manager.CheckpointManager` (patch, line 439): Potentially excessive mock: codeframe.lib.checkpoint_manager.CheckpointManager
  - `codeframe.lib.context_manager.ContextManager` (patch, line 440): Potentially excessive mock: codeframe.lib.context_manager.ContextManager
  - `unspecified` (Mock, line 450): Direct Mock object creation
  - `unspecified` (Mock, line 452): Direct Mock object creation
  - `unspecified` (Mock, line 453): Direct Mock object creation

### `TestProjectStartWithExistingPRD.test_start_resumes_when_prd_exists`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:105`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 104): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 108): Direct Mock object creation
  - `unspecified` (Mock, line 109): Direct Mock object creation

### `TestProjectStartWithExistingPRD.test_start_does_not_call_start_discovery_when_prd_exists`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:134`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 133): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 136): Direct Mock object creation
  - `unspecified` (Mock, line 137): Direct Mock object creation
  - `unspecified` (Mock, line 138): Direct Mock object creation

### `TestProjectStartWithoutPRD.test_start_begins_discovery_when_no_prd`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:152`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 151): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 155): Direct Mock object creation
  - `unspecified` (Mock, line 156): Direct Mock object creation
  - `unspecified` (Mock, line 157): Direct Mock object creation

### `TestProjectStartWithoutPRD.test_start_begins_discovery_when_prd_is_none`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:175`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 174): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 177): Direct Mock object creation
  - `unspecified` (Mock, line 178): Direct Mock object creation
  - `unspecified` (Mock, line 179): Direct Mock object creation

### `TestProjectStartErrorHandling.test_start_rollback_on_prd_load_error`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:214`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 213): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 217): Direct Mock object creation
  - `unspecified` (Mock, line 218): Direct Mock object creation

### `TestProjectStartIntegration.test_start_caches_leadagent_for_get_lead_agent`
- **File**: `/home/user/codeframe/tests/core/test_project_start.py:291`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.lead_agent.LeadAgent` (patch, line 290): Potentially excessive mock: codeframe.agents.lead_agent.LeadAgent
  - `unspecified` (Mock, line 293): Direct Mock object creation
  - `unspecified` (Mock, line 294): Direct Mock object creation

### `test_worker_agent_initialization`
- **File**: `/home/user/codeframe/tests/e2e/test_full_workflow.py:159`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (MagicMock, line 202): Direct Mock object creation
  - `unspecified` (MagicMock, line 203): Direct Mock object creation
  - `codeframe.agents.worker_agent.AsyncAnthropic` (patch, line 208): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 209): Direct Mock object creation

### `TestBackendWorkerAgentIntegration.test_execute_task_integration_with_mocked_llm`
- **File**: `/home/user/codeframe/tests/integration/test_backend_worker_agent_integration.py:189`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 219): Direct Mock object creation
  - `anthropic.AsyncAnthropic` (patch, line 232): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 233): Direct Mock object creation
  - `unspecified` (Mock, line 236): Direct Mock object creation
  - `unspecified` (Mock, line 238): Direct Mock object creation
  - `codeframe.testing.test_runner.TestRunner.run_tests` (patch, line 266): Potentially excessive mock: codeframe.testing.test_runner.TestRunner.run_tests

### `TestBackendWorkerAgentIntegration.test_execute_task_handles_file_operation_errors`
- **File**: `/home/user/codeframe/tests/integration/test_backend_worker_agent_integration.py:303`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 332): Direct Mock object creation
  - `anthropic.AsyncAnthropic` (patch, line 344): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 345): Direct Mock object creation
  - `unspecified` (Mock, line 348): Direct Mock object creation
  - `unspecified` (Mock, line 350): Direct Mock object creation

### `TestBackendWorkerAgentIntegration.test_multiple_task_execution_sequence`
- **File**: `/home/user/codeframe/tests/integration/test_backend_worker_agent_integration.py:410`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 453): Direct Mock object creation
  - `anthropic.AsyncAnthropic` (patch, line 465): Acceptable mock: external LLM API
  - `unspecified` (AsyncMock, line 466): Direct Mock object creation
  - `unspecified` (Mock, line 470): Direct Mock object creation
  - `unspecified` (Mock, line 472): Direct Mock object creation
  - `unspecified` (Mock, line 489): Direct Mock object creation
  - `unspecified` (Mock, line 491): Direct Mock object creation
  - `codeframe.testing.test_runner.TestRunner.run_tests` (patch, line 515): Potentially excessive mock: codeframe.testing.test_runner.TestRunner.run_tests

### `test_mvp_completion_full_workflow_success`
- **File**: `/home/user/codeframe/tests/integration/test_mvp_completion_workflow.py:107`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 188): Direct Mock object creation
  - `unspecified` (AsyncMock, line 191): Direct Mock object creation
  - `unspecified` (Mock, line 192): Direct Mock object creation

### `TestNotificationWorkflow.test_sync_blocker_triggers_desktop_notification`
- **File**: `/home/user/codeframe/tests/integration/test_notification_workflow.py:29`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 32): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 33): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 36): Direct Mock object creation
  - `unspecified` (AsyncMock, line 40): Direct Mock object creation

### `TestNotificationWorkflow.test_async_blocker_does_not_trigger_when_sync_only`
- **File**: `/home/user/codeframe/tests/integration/test_notification_workflow.py:94`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 97): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 98): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 101): Direct Mock object creation
  - `unspecified` (AsyncMock, line 105): Direct Mock object creation

### `TestQualityGatesIntegration.test_quality_gate_workflow_review_failure`
- **File**: `/home/user/codeframe/tests/integration/test_quality_gates_integration.py:245`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 276): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 278): Direct Mock object creation
  - `unspecified` (Mock, line 281): Direct Mock object creation
  - `unspecified` (AsyncMock, line 290): Direct Mock object creation

### `TestQualityMetricsRecording.test_response_count_incremented_on_execute_task`
- **File**: `/home/user/codeframe/tests/integration/test_quality_tracker_integration.py:151`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (Mock, line 159): Direct Mock object creation
  - `unspecified` (Mock, line 160): Direct Mock object creation
  - `unspecified` (Mock, line 161): Direct Mock object creation

### `TestQualityGates.test_block_on_critical_review`
- **File**: `/home/user/codeframe/tests/lib/test_quality_gates.py:189`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.agents.review_agent.ReviewAgent` (patch, line 192): Potentially excessive mock: codeframe.agents.review_agent.ReviewAgent
  - `unspecified` (Mock, line 194): Direct Mock object creation
  - `unspecified` (Mock, line 197): Direct Mock object creation
  - `unspecified` (AsyncMock, line 205): Direct Mock object creation

### `test_build_codeframe_hooks_creates_tracker_if_none`
- **File**: `/home/user/codeframe/tests/lib/test_sdk_hooks.py:441`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.lib.sdk_hooks.SDK_AVAILABLE` (patch, line 444): Potentially excessive mock: codeframe.lib.sdk_hooks.SDK_AVAILABLE
  - `codeframe.lib.sdk_hooks.HookMatcher` (patch, line 445): Potentially excessive mock: codeframe.lib.sdk_hooks.HookMatcher
  - `codeframe.lib.metrics_tracker.MetricsTracker` (patch, line 446): Potentially excessive mock: codeframe.lib.metrics_tracker.MetricsTracker

### `TestWindowsNotification.test_sends_notification_with_win10toast`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:133`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `platform.system` (patch, line 131): Potentially excessive mock: platform.system
  - `codeframe.notifications.desktop.ToastNotifier` (patch, line 132): Potentially excessive mock: codeframe.notifications.desktop.ToastNotifier
  - `unspecified` (Mock, line 135): Direct Mock object creation

### `TestWindowsFallback.test_uses_plyer_when_win10toast_unavailable`
- **File**: `/home/user/codeframe/tests/notifications/test_desktop.py:152`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `platform.system` (patch, line 149): Potentially excessive mock: platform.system
  - `codeframe.notifications.desktop.ToastNotifier` (patch, line 150): Potentially excessive mock: codeframe.notifications.desktop.ToastNotifier
  - `codeframe.notifications.desktop.notification` (patch, line 151): Potentially excessive mock: codeframe.notifications.desktop.notification

### `TestNotificationRouter.test_routes_to_desktop_and_webhook`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:19`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 23): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 24): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 27): Direct Mock object creation
  - `unspecified` (AsyncMock, line 31): Direct Mock object creation

### `TestNotificationRouter.test_skips_desktop_when_disabled`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:49`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 52): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 53): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 56): Direct Mock object creation
  - `unspecified` (AsyncMock, line 59): Direct Mock object creation

### `TestNotificationRouter.test_skips_webhook_when_disabled`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:76`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 79): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 80): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 83): Direct Mock object creation
  - `unspecified` (AsyncMock, line 87): Direct Mock object creation

### `TestNotificationRouter.test_filters_sync_only_when_configured`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:104`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 107): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 108): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 111): Direct Mock object creation
  - `unspecified` (AsyncMock, line 115): Direct Mock object creation

### `TestNotificationRouter.test_sends_all_blockers_when_sync_only_false`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:141`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 144): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 145): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 148): Direct Mock object creation
  - `unspecified` (AsyncMock, line 152): Direct Mock object creation

### `TestNotificationRouter.test_continues_on_desktop_failure`
- **File**: `/home/user/codeframe/tests/notifications/test_router.py:178`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.notifications.router.DesktopNotificationService` (patch, line 181): Potentially excessive mock: codeframe.notifications.router.DesktopNotificationService
  - `codeframe.notifications.router.WebhookNotificationService` (patch, line 182): Potentially excessive mock: codeframe.notifications.router.WebhookNotificationService
  - `unspecified` (Mock, line 185): Direct Mock object creation
  - `unspecified` (AsyncMock, line 190): Direct Mock object creation

### `TestWebhookNotificationService.test_send_blocker_notification_sync_success`
- **File**: `/home/user/codeframe/tests/notifications/test_webhook_notifications.py:88`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 93): Direct Mock object creation
  - `unspecified` (MagicMock, line 95): Direct Mock object creation
  - `unspecified` (AsyncMock, line 98): Direct Mock object creation
  - `unspecified` (MagicMock, line 102): Direct Mock object creation
  - `aiohttp.ClientSession` (patch, line 107): Acceptable mock: external HTTP requests

### `TestWebhookNotificationService.test_send_blocker_notification_correct_payload`
- **File**: `/home/user/codeframe/tests/notifications/test_webhook_notifications.py:259`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 263): Direct Mock object creation
  - `unspecified` (MagicMock, line 265): Direct Mock object creation
  - `unspecified` (AsyncMock, line 268): Direct Mock object creation
  - `unspecified` (MagicMock, line 272): Direct Mock object creation
  - `aiohttp.ClientSession` (patch, line 277): Acceptable mock: external HTTP requests

### `TestWebhookNotificationService.test_send_blocker_notification_timeout_configured`
- **File**: `/home/user/codeframe/tests/notifications/test_webhook_notifications.py:298`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 302): Direct Mock object creation
  - `unspecified` (MagicMock, line 304): Direct Mock object creation
  - `unspecified` (AsyncMock, line 307): Direct Mock object creation
  - `unspecified` (MagicMock, line 311): Direct Mock object creation
  - `aiohttp.ClientSession` (patch, line 316): Acceptable mock: external HTTP requests

### `TestAnthropicProviderMessageSending.test_send_message_with_simple_conversation`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:61`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 60): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 64): Direct Mock object creation
  - `unspecified` (Mock, line 65): Direct Mock object creation
  - `unspecified` (Mock, line 66): Direct Mock object creation

### `TestAnthropicProviderMessageSending.test_send_message_with_multi_turn_conversation`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:87`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 86): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 90): Direct Mock object creation
  - `unspecified` (Mock, line 91): Direct Mock object creation
  - `unspecified` (Mock, line 92): Direct Mock object creation

### `TestAnthropicProviderTokenUsage.test_send_message_returns_token_usage`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:187`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 186): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 190): Direct Mock object creation
  - `unspecified` (Mock, line 191): Direct Mock object creation
  - `unspecified` (Mock, line 192): Direct Mock object creation

### `TestAnthropicProviderTokenUsage.test_send_message_handles_missing_usage_data`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:212`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 211): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 215): Direct Mock object creation
  - `unspecified` (Mock, line 216): Direct Mock object creation
  - `unspecified` (Mock, line 217): Direct Mock object creation

### `TestAnthropicProviderErrorHandling.test_send_message_handles_authentication_error`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:240`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 239): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 245): Direct Mock object creation
  - `unspecified` (Mock, line 247): Direct Mock object creation

### `TestAnthropicProviderErrorHandling.test_send_message_handles_rate_limit_error`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:261`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 260): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 266): Direct Mock object creation
  - `unspecified` (Mock, line 268): Direct Mock object creation

### `TestAnthropicProviderIntegration.test_complete_conversation_flow`
- **File**: `/home/user/codeframe/tests/providers/test_anthropic_provider.py:308`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `codeframe.providers.anthropic.Anthropic` (patch, line 307): Potentially excessive mock: codeframe.providers.anthropic.Anthropic
  - `unspecified` (Mock, line 311): Direct Mock object creation
  - `unspecified` (Mock, line 314): Direct Mock object creation
  - `unspecified` (Mock, line 315): Direct Mock object creation
  - `unspecified` (Mock, line 321): Direct Mock object creation
  - `unspecified` (Mock, line 322): Direct Mock object creation

### `TestSelfCorrectionLoop.test_self_correction_successful_on_first_attempt`
- **File**: `/home/user/codeframe/tests/testing/test_self_correction_integration.py:26`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 24): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 60): Direct Mock object creation
  - `unspecified` (AsyncMock, line 64): Direct Mock object creation
  - `unspecified` (Mock, line 68): Direct Mock object creation
  - `unspecified` (Mock, line 70): Direct Mock object creation
  - `unspecified` (Mock, line 87): Direct Mock object creation
  - `unspecified` (Mock, line 89): Direct Mock object creation

### `TestSelfCorrectionLoop.test_self_correction_exhausts_all_attempts`
- **File**: `/home/user/codeframe/tests/testing/test_self_correction_integration.py:149`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 147): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 181): Direct Mock object creation
  - `unspecified` (AsyncMock, line 185): Direct Mock object creation
  - `unspecified` (Mock, line 190): Direct Mock object creation
  - `unspecified` (Mock, line 192): Direct Mock object creation

### `TestSelfCorrectionLoop.test_self_correction_successful_on_second_attempt`
- **File**: `/home/user/codeframe/tests/testing/test_self_correction_integration.py:266`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 264): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 300): Direct Mock object creation
  - `unspecified` (AsyncMock, line 304): Direct Mock object creation
  - `unspecified` (Mock, line 308): Direct Mock object creation
  - `unspecified` (Mock, line 310): Direct Mock object creation
  - `unspecified` (Mock, line 322): Direct Mock object creation
  - `unspecified` (Mock, line 324): Direct Mock object creation
  - `unspecified` (Mock, line 340): Direct Mock object creation
  - `unspecified` (Mock, line 342): Direct Mock object creation

### `TestSelfCorrectionLoop.test_no_self_correction_when_tests_pass_initially`
- **File**: `/home/user/codeframe/tests/testing/test_self_correction_integration.py:403`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `anthropic.AsyncAnthropic` (patch, line 401): Acceptable mock: external LLM API
  - `unspecified` (Mock, line 437): Direct Mock object creation
  - `unspecified` (AsyncMock, line 441): Direct Mock object creation
  - `unspecified` (Mock, line 443): Direct Mock object creation
  - `unspecified` (Mock, line 445): Direct Mock object creation

### `TestWebSocketSubscriptionManager.test_get_subscribers_for_project`
- **File**: `/home/user/codeframe/tests/ui/test_websocket_integration.py:690`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 697): Direct Mock object creation
  - `unspecified` (AsyncMock, line 698): Direct Mock object creation
  - `unspecified` (AsyncMock, line 699): Direct Mock object creation

### `TestConnectionManagerBroadcast.test_broadcast_handles_send_error`
- **File**: `/home/user/codeframe/tests/ui/test_websocket_subscriptions.py:452`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 455): Direct Mock object creation
  - `unspecified` (AsyncMock, line 456): Direct Mock object creation
  - `unspecified` (AsyncMock, line 459): Direct Mock object creation
  - `unspecified` (AsyncMock, line 460): Direct Mock object creation

### `TestConcurrency.test_concurrent_connect_disconnect`
- **File**: `/home/user/codeframe/tests/ui/test_websocket_subscriptions.py:574`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (MagicMock, line 576): Direct Mock object creation
  - `unspecified` (AsyncMock, line 578): Direct Mock object creation
  - `unspecified` (AsyncMock, line 579): Direct Mock object creation
  - `unspecified` (AsyncMock, line 580): Direct Mock object creation

### `TestEdgeCases.test_broadcast_error_cleanup_is_atomic`
- **File**: `/home/user/codeframe/tests/ui/test_websocket_subscriptions.py:733`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (AsyncMock, line 736): Direct Mock object creation
  - `unspecified` (AsyncMock, line 737): Direct Mock object creation
  - `unspecified` (AsyncMock, line 740): Direct Mock object creation
  - `unspecified` (AsyncMock, line 741): Direct Mock object creation

### `TestIntegration.test_multi_agent_scenario`
- **File**: `/home/user/codeframe/tests/ui/test_websocket_subscriptions.py:821`
- **Recommendation**: Consider reducing mocking or converting to integration test
- **Mock Patterns**:
  - `unspecified` (MagicMock, line 824): Direct Mock object creation
  - `unspecified` (AsyncMock, line 826): Direct Mock object creation
  - `unspecified` (AsyncMock, line 827): Direct Mock object creation
  - `unspecified` (AsyncMock, line 828): Direct Mock object creation


---

## Recommendations

### For HIGH Severity Tests:
1. Convert to integration tests in `tests/integration/`
2. Use real database fixtures (`:memory:` SQLite)
3. Use real file operations in temp directories
4. Only mock external APIs (Anthropic, OpenAI, GitHub)

### For MEDIUM Severity Tests:
1. Review if mocking is necessary
2. Consider using real implementations where possible
3. Document why mocking is needed if kept

### General Guidelines:
- Unit tests: Focus on logic, mock external I/O only
- Integration tests: Use real components, mock only external services
- Never mock `execute_task()`, database operations, or quality gates in unit tests
