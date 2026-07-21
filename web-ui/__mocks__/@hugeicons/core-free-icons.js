// Test mock for @hugeicons/core-free-icons (1.x icon data package).
//
// In production, each icon is a readonly array of [tag, attrs] tuples (an
// `IconSvgElement`). For unit tests we don't need real SVG data — we just
// need a stable sentinel that the @hugeicons/react mock can identify. Each
// accessed `XxxIcon` property returns `{ __iconName: '<name>' }`, which the
// HugeiconsIcon mock renders as `<svg data-testid="icon-<name>" />`.
//
// A Proxy keeps this resilient to new icons being added without touching
// this file.

module.exports = new Proxy(
  {},
  {
    get(_target, prop) {
      if (typeof prop !== 'string') return undefined;
      // Non-string symbols (e.g. Symbol.toStringTag, inspect customs) → undefined.
      // Any string property access returns a stable sentinel object.
      return { __iconName: prop };
    },
  },
);
