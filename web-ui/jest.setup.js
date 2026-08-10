import '@testing-library/jest-dom';

// jsdom does not implement scrollIntoView
window.HTMLElement.prototype.scrollIntoView = jest.fn();

// jsdom ships no TextEncoder/TextDecoder, which every browser has. Node's are
// the same WHATWG implementation, so this makes the environment match reality
// rather than working around the gap in production code (#1077).
import { TextDecoder, TextEncoder } from 'util';

if (typeof global.TextDecoder === 'undefined') {
  global.TextDecoder = TextDecoder;
}
if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = TextEncoder;
}

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
    };
  },
  usePathname() {
    return '';
  },
  useSearchParams() {
    return new URLSearchParams();
  },
}));
