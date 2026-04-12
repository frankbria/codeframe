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
  // PRD components
  Upload04Icon: createIconMock('Upload04Icon'),
  MessageSearch01Icon: createIconMock('MessageSearch01Icon'),
  TaskEdit01Icon: createIconMock('TaskEdit01Icon'),
  ArtificialIntelligence01Icon: createIconMock('ArtificialIntelligence01Icon'),
  SentIcon: createIconMock('SentIcon'),
  // AppSidebar
  Home01Icon: createIconMock('Home01Icon'),
  Add01Icon: createIconMock('Add01Icon'),
  // PipelineProgressBar
  Tick01Icon: createIconMock('Tick01Icon'),
  // Task Board components
  PlayCircleIcon: createIconMock('PlayCircleIcon'),
  LinkCircleIcon: createIconMock('LinkCircleIcon'),
  ViewIcon: createIconMock('ViewIcon'),
  Search01Icon: createIconMock('Search01Icon'),
  CheckListIcon: createIconMock('CheckListIcon'),
  // Execution Monitor components
  Idea01Icon: createIconMock('Idea01Icon'),
  ArrowTurnBackwardIcon: createIconMock('ArrowTurnBackwardIcon'),
  CommandLineIcon: createIconMock('CommandLineIcon'),
  AlertDiamondIcon: createIconMock('AlertDiamondIcon'),
  WifiDisconnected01Icon: createIconMock('WifiDisconnected01Icon'),
  SidebarLeftIcon: createIconMock('SidebarLeftIcon'),
  ArrowDown01Icon: createIconMock('ArrowDown01Icon'),
  ArrowUp01Icon: createIconMock('ArrowUp01Icon'),
  StopIcon: createIconMock('StopIcon'),
  // AgentChatPanel
  ArrowRight01Icon: createIconMock('ArrowRight01Icon'),
  Alert01Icon: createIconMock('Alert01Icon'),
  // SplitPane
  ArrowLeft01Icon: createIconMock('ArrowLeft01Icon'),
  // Proof page
  InformationCircleIcon: createIconMock('InformationCircleIcon'),
  // FileTreePanel / DiffViewer
  FileAddIcon: createIconMock('FileAddIcon'),
  FileRemoveIcon: createIconMock('FileRemoveIcon'),
  // BlockerCard origin badges
  Settings01Icon: createIconMock('Settings01Icon'),
  UserCircle02Icon: createIconMock('UserCircle02Icon'),
};
