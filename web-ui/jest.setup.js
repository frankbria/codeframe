// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'

// Mock react-markdown to avoid ESM issues
jest.mock('react-markdown', () => {
  return function ReactMarkdown({ children }) {
    return children
  }
})
