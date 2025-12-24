/**
 * Manual mock for @hugeicons/react
 * This avoids ESM issues in Jest tests
 */

const React = require('react');

// Mock all icon exports
module.exports = {
  Download01Icon: (props) => React.createElement('svg', { 'data-testid': 'download-icon', ...props }),
  Cancel01Icon: (props) => React.createElement('svg', { 'data-testid': 'cancel-icon', ...props }),
  Tick01Icon: (props) => React.createElement('svg', { 'data-testid': 'tick-icon', ...props }),
  ArrowDown01Icon: (props) => React.createElement('svg', { 'data-testid': 'arrow-down-icon', ...props }),
  ArrowUp01Icon: (props) => React.createElement('svg', { 'data-testid': 'arrow-up-icon', ...props }),
};
