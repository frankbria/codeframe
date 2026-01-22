/**
 * Manual mock for @hugeicons/react
 * This avoids ESM issues in Jest tests
 */

const React = require('react');

// Helper to create mock icon component
const createIcon = (name) => (props) => React.createElement('svg', { 'data-testid': `${name}-icon`, ...props });

// Mock all icon exports
module.exports = {
  // UI component icons
  Download01Icon: createIcon('download'),
  Cancel01Icon: createIcon('cancel'),
  Tick01Icon: createIcon('tick'),
  ArrowDown01Icon: createIcon('arrow-down'),
  ArrowUp01Icon: createIcon('arrow-up'),

  // TaskStats icons
  CheckListIcon: createIcon('check-list'),
  CheckmarkCircle01Icon: createIcon('checkmark-circle'),
  Alert02Icon: createIcon('alert'),
  Loading03Icon: createIcon('loading'),

  // Dashboard icons
  UserGroupIcon: createIcon('user-group'),
  WorkHistoryIcon: createIcon('work-history'),
  TestTube01Icon: createIcon('test-tube'),
  CheckmarkSquare01Icon: createIcon('checkmark-square'),
  BotIcon: createIcon('bot'),
  Logout02Icon: createIcon('logout'),
  GitCommitIcon: createIcon('git-commit'),
  AnalyticsUpIcon: createIcon('analytics-up'),
  ClipboardIcon: createIcon('clipboard'),
  Search01Icon: createIcon('search'),
  Target02Icon: createIcon('target'),
  FloppyDiskIcon: createIcon('floppy-disk'),
  Add01Icon: createIcon('add'),
};
