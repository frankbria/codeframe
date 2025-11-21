const nextJest = require('next/jest')

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files in your test environment
  dir: './',
})

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'jest-environment-jsdom',
  testPathIgnorePatterns: ['/node_modules/', '/__tests__/fixtures/'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  transformIgnorePatterns: [
    '/node_modules/(?!(.pnpm|react-markdown|vfile|vfile-message|unist-.*|unified|bail|is-plain-obj|trough|remark-.*|mdast-util-.*|micromark.*|decode-named-character-reference|character-entities|property-information|hast-util-whitespace|space-separated-tokens|comma-separated-tokens|pretty-bytes|msw|@mswjs|strict-event-emitter|until-async|@bundled-es-modules|@open-draft|outvariant|cookie))',
  ],
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.{js,jsx,ts,tsx}',
    '!src/**/__tests__/**',
  ],
  coverageThreshold: {
    // Specific thresholds for cf-26 components
    './src/components/PRDModal.tsx': {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    './src/components/TaskTreeView.tsx': {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    // Specific thresholds for cf-17.2 components
    './src/components/ProgressBar.tsx': {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    './src/components/PhaseIndicator.tsx': {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    './src/components/DiscoveryProgress.tsx': {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
    // Specific thresholds for cf-14.2 components
    './src/components/ChatInterface.tsx': {
      branches: 85,
      functions: 85,
      lines: 85,
      statements: 85,
    },
    // Specific thresholds for 007-context-management components
    './src/components/context/ContextItemList.tsx': {
      branches: 85,
      functions: 100,
      lines: 100,
      statements: 85,
    },
    './src/components/context/ContextTierChart.tsx': {
      branches: 85,
      functions: 100,
      lines: 100,
      statements: 85,
    },
  },
}

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig)
