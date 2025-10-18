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
