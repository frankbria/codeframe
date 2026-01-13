/**
 * Browser-Specific Configuration for E2E Tests
 *
 * This module centralizes all browser-specific settings, timeouts, and quirk flags.
 * Import these configurations in test utilities and test files to handle cross-browser
 * differences consistently.
 *
 * Key browser differences addressed:
 * - Firefox: Slower CSS rendering, NS_BINDING_ABORTED errors during navigation
 * - WebKit: Delayed element rendering, localStorage timing issues
 * - Mobile: Touch events required, smaller viewports need scroll handling
 */

/**
 * Browser-specific timeout configurations
 *
 * Chromium is the baseline. Other browsers have multipliers applied based on
 * observed performance characteristics.
 *
 * - Firefox: +50% for CSS rendering and form validation
 * - WebKit: +40% for element stabilization and animations
 * - Mobile: +50% for touch event registration and viewport adjustments
 */
export const BROWSER_TIMEOUTS = {
  chromium: {
    action: 10000,      // Default actionTimeout
    expect: 5000,       // Default expect timeout
    navigation: 30000,  // Page navigation timeout
    formValidation: 3000,
    animation: 500,
  },
  firefox: {
    action: 15000,      // +50% for slower CSS rendering
    expect: 8000,       // +60% for async form validation
    navigation: 45000,  // +50% for network handling
    formValidation: 5000,  // Firefox renders validation messages asynchronously
    animation: 800,     // CSS transitions take longer
  },
  webkit: {
    action: 14000,      // +40% for element stabilization
    expect: 7000,       // +40% for delayed rendering
    navigation: 40000,  // +33% for Safari's network stack
    formValidation: 4000,
    animation: 700,     // WebKit animation timing differences
  },
  mobile: {
    action: 15000,      // +50% for touch event registration
    expect: 10000,      // +100% for viewport stabilization
    navigation: 60000,  // +100% for mobile network handling
    formValidation: 5000,
    animation: 1000,    // Mobile animations may be slower
  },
} as const;

/**
 * Browser quirk flags
 *
 * These flags indicate which workarounds are needed for each browser.
 * Use these to conditionally apply browser-specific handling in tests.
 */
export const BROWSER_QUIRKS = {
  firefox: {
    /** Firefox needs extra wait for async form validation rendering */
    needsFormValidationWait: true,
    /** Firefox's NS_BINDING_ABORTED error during navigation is benign */
    hasNSBindingAborted: true,
    /** Firefox may need reducedMotion for consistent animation timing */
    needsReducedMotion: true,
    /** Firefox click events may need explicit wait for element stability */
    needsClickStability: false,
    /** Firefox localStorage is synchronous but needs reload for visibility */
    hasDelayedLocalStorage: false,
  },
  webkit: {
    /** WebKit elements may not be stable immediately after appearing */
    needsElementStabilityWait: true,
    /** WebKit localStorage writes may not be immediately readable */
    hasDelayedLocalStorage: true,
    /** WebKit forms need click-then-fill pattern for reliable input */
    needsClickBeforeFill: true,
    /** WebKit animations need explicit completion wait */
    needsAnimationWait: true,
    /** WebKit needs extra time after navigation for DOM stability */
    needsPostNavigationWait: true,
  },
  mobile: {
    /** Mobile browsers require touch events instead of mouse clicks */
    needsTouchEvents: true,
    /** Mobile viewports need scroll into view before interaction */
    requiresScrollIntoView: true,
    /** Mobile may have hamburger menu instead of full navigation */
    hasResponsiveMenu: true,
    /** Mobile viewport may need stabilization after orientation/resize */
    needsViewportStabilization: true,
    /** Some features are desktop-only (hover states, etc.) */
    hasLimitedFeatures: true,
  },
  chromium: {
    /** Chromium is the baseline - no special handling needed */
    needsFormValidationWait: false,
    hasNSBindingAborted: false,
    needsElementStabilityWait: false,
    hasDelayedLocalStorage: false,
    needsTouchEvents: false,
    requiresScrollIntoView: false,
  },
} as const;

/**
 * Error patterns to filter by browser
 *
 * These are errors that appear in specific browsers but are not actual failures.
 * Use with filterExpectedErrors() in test-utils.ts.
 */
export const BROWSER_EXPECTED_ERRORS = {
  firefox: [
    'NS_BINDING_ABORTED',           // Normal during navigation
    'AbortError',                   // Request abort during navigation
    'NetworkError when attempting', // Sometimes appears during fast navigation
  ],
  webkit: [
    'Failed to load resource',      // Sometimes appears during rapid navigation
    'Load request cancelled',       // WebKit's equivalent of NS_BINDING_ABORTED
    'cancelled',                    // Generic cancellation error
  ],
  mobile: [
    'touch-action',                 // Touch action warnings
  ],
  chromium: [],                     // Baseline - no special filtering
  all: [
    'net::ERR_ABORTED',             // Normal when navigation cancels pending requests
    'Failed to fetch RSC payload',   // Next.js RSC during navigation
  ],
} as const;

/**
 * Mobile device viewport configurations
 *
 * These match Playwright's device definitions but are exported here for
 * custom viewport handling in tests.
 */
export const MOBILE_VIEWPORTS = {
  'Mobile Chrome': { width: 393, height: 851, isMobile: true, hasTouch: true },
  'Mobile Safari': { width: 390, height: 844, isMobile: true, hasTouch: true },
  'Pixel 5': { width: 393, height: 851, isMobile: true, hasTouch: true },
  'iPhone 12': { width: 390, height: 844, isMobile: true, hasTouch: true },
  'iPhone 13': { width: 390, height: 844, isMobile: true, hasTouch: true },
  'Galaxy S21': { width: 360, height: 800, isMobile: true, hasTouch: true },
} as const;

/**
 * Browser project names as used in Playwright config
 */
export const BROWSER_PROJECTS = {
  CHROMIUM: 'chromium',
  FIREFOX: 'firefox',
  WEBKIT: 'webkit',
  MOBILE_CHROME: 'Mobile Chrome',
  MOBILE_SAFARI: 'Mobile Safari',
} as const;

export type BrowserName = 'chromium' | 'firefox' | 'webkit';
export type MobileProjectName = 'Mobile Chrome' | 'Mobile Safari';
export type ProjectName = BrowserName | MobileProjectName;
