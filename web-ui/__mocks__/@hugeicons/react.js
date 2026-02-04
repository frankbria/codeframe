const React = require('react');

const createIconMock = (name) => {
  const IconComponent = React.forwardRef((props, ref) => {
    return React.createElement('svg', {
      'data-testid': `icon-${name}`,
      ref,
      ...props,
    });
  });
  IconComponent.displayName = name;
  return IconComponent;
};

module.exports = {
  // WorkspaceHeader
  Folder01Icon: createIconMock('Folder01Icon'),
  Loading03Icon: createIconMock('Loading03Icon'),
  // WorkspaceStatsCards
  CodeIcon: createIconMock('CodeIcon'),
  Task01Icon: createIconMock('Task01Icon'),
  PlayIcon: createIconMock('PlayIcon'),
  // QuickActions
  FileEditIcon: createIconMock('FileEditIcon'),
  GitBranchIcon: createIconMock('GitBranchIcon'),
  // RecentActivityFeed
  Time01Icon: createIconMock('Time01Icon'),
  CheckmarkCircle01Icon: createIconMock('CheckmarkCircle01Icon'),
  Alert02Icon: createIconMock('Alert02Icon'),
  // WorkspaceSelector
  Cancel01Icon: createIconMock('Cancel01Icon'),
};
