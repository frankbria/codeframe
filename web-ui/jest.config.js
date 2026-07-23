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
};

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig);
