// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'
import { TextEncoder, TextDecoder } from 'util'
import 'whatwg-fetch'

// Polyfill for TextEncoder/TextDecoder (required by MSW)
global.TextEncoder = TextEncoder
global.TextDecoder = TextDecoder

// Polyfill for Request/Response (required by MSW in Node environment)
if (typeof global.Request === 'undefined') {
  global.Request = class Request {}
}
if (typeof global.Response === 'undefined') {
  global.Response = class Response {}
}
if (typeof global.Headers === 'undefined') {
  global.Headers = class Headers {}
}
if (typeof global.BroadcastChannel === 'undefined') {
  global.BroadcastChannel = class BroadcastChannel {
    constructor(name) {
      this.name = name
    }
    postMessage() {}
    close() {}
    addEventListener() {}
    removeEventListener() {}
  }
}

// Mock react-markdown to avoid ESM issues
jest.mock('react-markdown', () => {
  return function ReactMarkdown({ children }) {
    return children
  }
})

// Mock @hugeicons/react - create stub components for all icons
jest.mock('@hugeicons/react', () => {
  const React = require('react')

  // Generic icon component factory
  const createIconMock = (name) => {
    const IconComponent = React.forwardRef(({ className, ...props }, ref) =>
      React.createElement('svg', {
        ref,
        className,
        'data-testid': name,
        'aria-hidden': 'true',
        ...props
      })
    )
    IconComponent.displayName = name
    return IconComponent
  }

  // List of all icons used in the codebase
  const iconNames = [
    'Add01Icon',
    'Alert02Icon',
    'AlertCircleIcon',
    'AlertDiamondIcon',
    'AnalyticsUpIcon',
    'ArrowDown01Icon',
    'ArrowRight01Icon',
    'ArrowUp01Icon',
    'Award01Icon',
    'BotIcon',
    'Cancel01Icon',
    'Cancel02Icon',
    'CheckListIcon',
    'CheckmarkCircle01Icon',
    'CheckmarkSquare01Icon',
    'CircleIcon',
    'ClipboardIcon',
    'Download01Icon',
    'FloppyDiskIcon',
    'GitBranchIcon',
    'GitCommitIcon',
    'GitPullRequestIcon',
    'HelpCircleIcon',
    'Idea01Icon',
    'Link01Icon',
    'Loading03Icon',
    'Logout02Icon',
    'RocketIcon',
    'Search01Icon',
    'Target02Icon',
    'TaskEdit01Icon',
    'TestTube01Icon',
    'Tick01Icon',
    'Time01Icon',
    'UserGroupIcon',
    'WorkHistoryIcon',
    'Wrench01Icon',
  ]

  // Create mock object with all icons
  const mocks = {}
  iconNames.forEach(name => {
    mocks[name] = createIconMock(name)
  })

  return mocks
})
