# CodeFRAME v2 Critical Gap Implementation Plan

**Status**: 🚧 Implementation Ready  
**Date**: 2026-01-17  
**Target**: Address critical CLI workflow gaps  
**Timeline**: 4-week intensive implementation sprint  

---

## 🎯 Implementation Objectives

Transform the CodeFRAME CLI from a theoretically complete workflow into a reliably usable tool by addressing the most critical gaps that would cause real users to abandon the tool.

**Success Criteria**:
- New users can successfully complete full workflow without hitting authentication or environment failures
- Users can recover gracefully from partial failures without losing all progress
- The CLI provides helpful error recovery guidance and automated fix suggestions

---

## 📅 Sprint Timeline

### Week 1-2: Foundation Infrastructure (Critical)

### 🔐 Week 1: Credential Management System

#### Day 1-2: Core Credential Infrastructure
**Tasks**:
- Implement `codeframe/core/credentials.py`
- Create secure credential storage (encrypted file-based initially)
- Define credential provider interfaces

**Files to Create**:
```python
# codeframe/core/credentials.py
class CredentialManager:
    def store(self, provider: str, key: str, encrypt: bool = True)
    def retrieve(self, provider: str) -> Optional[str]
    def list_providers(self) -> Dict[str, CredentialMetadata]
    def validate(self, provider: str) -> bool
    def rotate(self, provider: str) -> str
```

**CLI Commands to Implement**:
```bash
# codeframe/cli/auth_commands.py
codeframe auth setup                    # Interactive credential configuration
codeframe auth list                     # Show all configured providers
codeframe auth validate <provider>        # Test specific provider credential
codeframe auth rotate <provider>           # Secure key rotation
codeframe auth remove <provider>           # Remove stored credential
```

#### Day 3-4: Provider Integration
**Tasks**:
- Integrate credential manager with existing LLM adapters
- Add GitHub provider integration for PR operations
- Implement credential validation for each provider type
- Add credential health check to `init` flow

**Integration Points**:
- Modify `codeframe/core/agents_config.py` to use CredentialManager
- Update `codeframe/core/git_integration.py` to retrieve GitHub tokens
- Enhance `prd generate` to validate LLM credentials before starting

#### Day 5: Testing & Documentation
**Tasks**:
- Comprehensive credential management testing
- Security audit of credential storage
- Documentation for all auth commands
- Integration testing with existing workflow

### 🔧 Week 2: Environment Validation & State Management

#### Day 6-7: Environment Validation Framework
**Files to Create**:
```python
# codeframe/core/environment.py
class EnvironmentValidator:
    def validate_all(self, workspace) -> ValidationResult
    def check_tools(self, required_tools: List[str]) -> ToolStatus
    def suggest_fixes(self, issues: List[Issue]) -> List[FixSuggestion]
    def auto_install(self, tool: str, consent: bool = False) -> bool
```

**CLI Commands**:
```bash
# codeframe/cli/env_commands.py  
codeframe env check                   # Quick validation
codeframe env doctor                    # Comprehensive health check
codeframe env install-missing <tool>    # Install specific missing tool
codeframe env auto-install                # Install all missing tools (with consent)
```

**Tool Detection Matrix**:
```python
REQUIRED_TOOLS = {
    'python': ['pytest', 'ruff', 'mypy'],
    'typescript': ['jest', 'eslint', 'prettier'], 
    'generic': ['git', 'node', 'python3']
}

AUTO_INSTALLABLE = {
    'pytest': 'pip install pytest',
    'ruff': 'pip install ruff', 
    'eslint': 'npm install -g eslint'
}
```

#### Day 8-9: Incremental State Persistence
**Enhancements to Existing**:
```python
# Enhance codeframe/core/conductor.py
class BatchConductor:
    def __init__(self, workspace, auto_checkpoint_interval=5):
        self.auto_checkpoint_interval = auto_checkpoint_interval
    
    def execute_with_checkpoints(self, batch):
        # Auto-checkpoint every N tasks or time interval
        # Emergency state backup before each task
        # Recovery snapshots after task completion
```

**New Features**:
- `codeframe work batch --auto-checkpoint N`
- Emergency recovery file creation
- Partial batch state restoration
- Corruption detection and repair

#### Day 10: Integration & Testing
**Tasks**:
- Integrate environment validation into `init` flow
- Add credential checking to batch execution startup
- Test complete enhanced flow
- Performance impact assessment

---

### Week 3-4: Robustness Enhancements

### ⚡ Week 3: Advanced Recovery & Conflict Resolution

#### Day 11-13: Granular Recovery System
**Files to Enhance**:
```python
# Enhance codeframe/core/checkpoints.py  
class CheckpointManager:
    def create_task_checkpoint(self, task_id, state) -> TaskCheckpoint
    def rollback_task(self, task_id) -> bool
    def rollback_last_n_tasks(self, n) -> bool
    def emergency_recovery(self) -> RecoveryOptions
```

**New CLI Commands**:
```bash
codeframe rollback task <task-id>      # Undo specific task
codeframe rollback last <n>             # Undo last N tasks  
codeframe emergency-recovery             # Interactive recovery wizard
codeframe rollback batch <batch-id>    # Restore batch to safe state
```

#### Day 14-15: Dependency Management
**Enhancements**:
```python
# Enhance codeframe/core/dependency_analyzer.py
class DependencyAnalyzer:
    def detect_conflicts(self, tasks) -> List[Conflict]
    def detect_circular_deps(self, tasks) -> List[CircularDependency]
    def suggest_resolution(self, conflict) -> Resolution
    def visualize_dependencies(self, tasks) -> DependencyGraph
```

**New CLI Commands**:
```bash
codeframe tasks analyze --conflicts    # Detect dependency issues
codeframe tasks resolve-conflicts       # Interactive resolution
codeframe tasks visualize-deps         # Show dependency graph
codeframe tasks suggest-order           # Optimize execution order
```

#### Day 16-17: Integration Testing Framework
**Files to Create**:
```python
# codeframe/core/integration_testing.py
class IntegrationTester:
    def setup_test_environment(self) -> TestEnvironment
    def run_integration_tests(self, changes) -> TestResults
    def check_compatibility(self, changes) -> CompatibilityReport
    def detect_breaking_changes(self) -> List[BreakingChange]
```

**CLI Commands**:
```bash
codeframe test integration              # Run integration test suite
codeframe test compatibility             # Check against existing code
codeframe test breaking-changes         # Detect potential breakages
codeframe test generate-fixes           # Generate fixes for failed tests
```

#### Day 18: Testing & Integration
**Tasks**:
- Comprehensive integration testing
- Performance benchmarking
- Error handling validation
- Documentation updates

---

## 🔧 Week 4: Polish & Documentation

### 📊 Days 19-21: Enhanced Monitoring & Debugging

#### Advanced Monitoring
**Enhancements**:
```python
# codeframe/core/monitoring.py
class BatchMonitor:
    def实时监控(self, batch_id) -> MonitoringData
    def calculate_eta(self, batch) -> EstimatedTime
    def generate_progress_report(self, batch) -> ProgressReport
    def detect_anomalies(self, batch) -> List[Anomaly]
```

**CLI Commands**:
```bash
codeframe monitor <batch-id>           # Enhanced real-time monitoring
codeframe debug task <task-id>          # Deep task debugging
codeframe logs task <task-id> --verbose  # Detailed task logs
codeframe performance report            # Performance analysis
```

### 🎛️ Days 22-24: Template & Profile System

#### Template Management
**Files to Create**:
```python
# codeframe/core/templates.py
class TemplateManager:
    def save_task_template(self, name, template) -> bool
    def save_prd_template(self, name, template) -> bool
    def save_workflow_template(self, name, template) -> bool
    def list_templates(self, type) -> List[Template]
    def apply_template(self, name, context) -> TemplateResult
```

**CLI Commands**:
```bash
codeframe templates save <name> <type>   # Save current as template
codeframe templates list <type>           # List available templates
codeframe templates apply <name>          # Apply template
codeframe profile create <name>           # Create project profile
codeframe profile use <name>              # Switch to profile
```

#### Day 25: Final Integration & Testing
**Tasks**:
- End-to-end workflow testing with all enhancements
- Performance optimization
- Security audit of new components
- User acceptance testing with sample projects

---

## 📋 Implementation Checklist

### Phase 1: Foundation (Week 1-2)
- [ ] Credential management core implemented
- [ ] Auth CLI commands created and tested
- [ ] Environment validation framework built
- [ ] Auto-checkpointing integrated into batch execution
- [ ] All new features tested independently
- [ ] Security audit passed for credential storage
- [ ] Documentation for all new commands

### Phase 2: Robustness (Week 3-4)
- [ ] Granular rollback system operational
- [ ] Dependency conflict resolution working
- [ ] Integration testing framework functional
- [ ] Enhanced monitoring and debugging tools
- [ ] Template and profile system complete
- [ ] Performance benchmarks established
- [ ] Full end-to-end testing completed

### Cross-Cutting Requirements
- [ ] All new CLI commands follow existing patterns
- [ ] Error messages are helpful and actionable
- [ ] All features work without FastAPI server
- [ ] Backward compatibility maintained
- [ ] Comprehensive test coverage (>90%)
- [ ] Documentation complete and accurate

---

## 🎯 Success Metrics

### Quantitative Metrics
- **User Success Rate**: >95% of users can complete full workflow on first attempt
- **Error Recovery Time**: <5 minutes to recover from common failures  
- **Tool Detection Accuracy**: >99% of required tools correctly detected
- **Checkpoint Reliability**: <1% checkpoint failure rate
- **Credential Validation**: 100% of credential issues detected before execution

### Qualitative Metrics
- **User Feedback**: Positive feedback on error handling and recovery
- **Documentation Clarity**: All commands clearly documented with examples
- **Performance**: No significant performance regression from new features
- **Security**: Credential storage meets security best practices

---

## 🚀 Risk Mitigation

### Technical Risks
- **Credential Storage Security**: Use platform-native keyring when possible
- **Backward Compatibility**: Maintain existing command patterns
- **Performance**: Monitor impact of additional validation/checkpointing

### Project Risks  
- **Timeline Aggressiveness**: Focus on critical gaps first, defer optional features
- **Quality vs Speed**: Maintain code quality while implementing quickly
- **User Feedback**: Collect user feedback early and adjust priorities

---

## 📚 Implementation Resources

### Required Dependencies
- `keyring` - Secure credential storage
- `cryptography` - Credential encryption (if not using keyring)
- `psutil` - System monitoring for performance
- `rich` - Enhanced CLI output (already used)

### Reference Implementations
- GitHub CLI credential management patterns
- AWS CLI secure credential storage
- Docker Compose environment validation
- Kubernetes tool detection and validation

---

## 🎉 Expected Outcome

After this 4-week implementation sprint, CodeFRAME v2 will transform from a theoretically capable tool into a reliably usable CLI that:

1. **Never surprises users with missing credentials** - Proactive validation and clear setup guidance
2. **Never loses hours of work unexpectedly** - Robust state persistence and recovery  
3. **Provides clear paths forward from any failure** - Granular rollback and automated fix suggestions
4. **Works reliably across different environments** - Comprehensive tool detection and validation
5. **Guides users through complex workflows** - Rich monitoring and debugging capabilities

This addresses the critical gap between "complete workflow on paper" and "reliable tool in practice."