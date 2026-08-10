const nextJest = require('next/jest');

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files
  dir: './',
});

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@hugeicons/react$': '<rootDir>/__mocks__/@hugeicons/react.js',
    '^@hugeicons/core-free-icons$': '<rootDir>/__mocks__/@hugeicons/core-free-icons.js',
  },
  testMatch: ['**/__tests__/**/*.[jt]s?(x)', '**/?(*.)+(spec|test).[jt]s?(x)'],
  testPathIgnorePatterns: [
    '/node_modules/',
    '/.next/',
    'src/__tests__/utils/test-helpers',  // Shared test utilities, not a test suite
  ],
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
    '!src/types/**/*',
  ],
  // Jest 30 dropped 'json-summary' from the default reporters; CI's coverage
  // threshold gate reads coverage/coverage-summary.json, so request it explicitly.
  coverageReporters: ['json', 'json-summary', 'lcov', 'text', 'clover'],
  // Per-file floor for DiscoveryPanel, which sat at 0% (issue #965). The
  // repo-wide gate is a 65% check in CI; this is enforced by the runner so
  // `npm run test:coverage` fails locally too. Set below the achieved 94%/73%
  // so ordinary refactoring does not trip it — it guards against the coverage
  // *disappearing*, not against small movements.
  //
  // Deliberately only this file. A per-file threshold also fails when someone
  // runs `--coverage` over a subset that excludes the file, so each entry is a
  // small DX tax. src/lib/api.ts is not listed because its contract suite has
  // a stronger, subset-safe guard: a test that fails when a new *Api namespace
  // is exported without contract cases.
  coverageThreshold: {
    './src/components/prd/DiscoveryPanel.tsx': {
      statements: 85,
      branches: 65,
      functions: 90,
      lines: 85,
    },
  },
};

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig);
