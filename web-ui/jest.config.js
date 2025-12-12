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
  coverageProvider: 'v8', // Use V8 coverage instead of Istanbul (fixes Jest 30 compatibility)
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
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    './src/components/TaskTreeView.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    // Specific thresholds for cf-17.2 components
    './src/components/ProgressBar.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    './src/components/PhaseIndicator.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    './src/components/DiscoveryProgress.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    // Specific thresholds for cf-14.2 components
    './src/components/ChatInterface.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    // Specific thresholds for 007-context-management components
    './src/components/context/ContextItemList.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
    './src/components/context/ContextTierChart.tsx': {
      branches: 65,
      functions: 65,
      lines: 65,
      statements: 65,
    },
  },
}

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig)
