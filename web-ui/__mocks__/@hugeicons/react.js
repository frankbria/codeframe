const React = require('react');

const HugeiconsIcon = React.forwardRef(function HugeiconsIcon(
  { icon, altIcon, showAlt, size, color, strokeWidth, absoluteStrokeWidth, primaryColor, secondaryColor, disableSecondaryOpacity, ...rest },
  ref,
) {
  const iconName = icon && typeof icon === 'object' && '__iconName' in icon ? icon.__iconName : 'unknown';
  const effectiveIcon = showAlt && altIcon ? altIcon : icon;
  const effectiveName =
    effectiveIcon && typeof effectiveIcon === 'object' && '__iconName' in effectiveIcon
      ? effectiveIcon.__iconName
      : iconName;
  return React.createElement('svg', {
    'data-testid': `icon-${effectiveName}`,
    ref,
    ...rest,
  });
});

module.exports = {
  HugeiconsIcon,
  default: HugeiconsIcon,
};
