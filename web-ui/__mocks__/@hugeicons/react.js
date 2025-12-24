/**
 * Manual mock for @hugeicons/react
 * This avoids ESM issues in Jest tests
 */

const React = require('react');

// Mock all icon exports
module.exports = {
  Download01Icon: (props) => React.createElement('svg', { 'data-testid': 'download-icon', ...props }),
  // Add other icons as they are used in components
};
