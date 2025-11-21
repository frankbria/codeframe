/**
 * Unit tests for ContextTierChart component (T065)
 *
 * Tests:
 * - Chart renders with valid data
 * - HOT/WARM/COLD tier counts display
 * - Bar chart visualization
 * - Responsive container
 * - Color coding validation
 * - Empty/zero data handling
 * - Legend display
 * - Token distribution breakdown
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { ContextTierChart } from '../../../src/components/context/ContextTierChart';
import type { ContextStats } from '../../../src/types/context';

describe('ContextTierChart', () => {
  // Mock stats with typical distribution
  const mockStats: ContextStats = {
    agent_id: 'test-agent-001',
    project_id: 123,
    hot_count: 20,
    warm_count: 50,
    cold_count: 30,
    total_count: 100,
    hot_tokens: 15000,
    warm_tokens: 25000,
    cold_tokens: 10000,
    total_tokens: 50000,
    token_usage_percentage: 27.78,
    calculated_at: '2025-11-14T10:30:00Z',
  };

  describe('Rendering with Valid Data', () => {
    it('test_renders_chart_title', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT
      expect(screen.getByText('Tier Distribution')).toBeInTheDocument();
    });

    it('test_renders_all_tier_bars', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Find bar elements by class name
      const container = screen.getByText('Tier Distribution').parentElement;
      expect(container).toBeInTheDocument();

      const hotBar = container!.querySelector('.chart-bar.hot');
      const warmBar = container!.querySelector('.chart-bar.warm');
      const coldBar = container!.querySelector('.chart-bar.cold');

      expect(hotBar).toBeInTheDocument();
      expect(warmBar).toBeInTheDocument();
      expect(coldBar).toBeInTheDocument();
    });

    it('test_chart_bar_widths_calculated_correctly', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Verify bar widths match percentages
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot') as HTMLElement;
      const warmBar = container!.querySelector('.chart-bar.warm') as HTMLElement;
      const coldBar = container!.querySelector('.chart-bar.cold') as HTMLElement;

      // Expected: hot=20%, warm=50%, cold=30%
      expect(hotBar.style.width).toBe('20%');
      expect(warmBar.style.width).toBe('50%');
      expect(coldBar.style.width).toBe('30%');
    });

    it('test_chart_bars_have_hover_titles', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Verify title attributes for tooltips
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot') as HTMLElement;
      const warmBar = container!.querySelector('.chart-bar.warm') as HTMLElement;
      const coldBar = container!.querySelector('.chart-bar.cold') as HTMLElement;

      expect(hotBar.getAttribute('title')).toBe('HOT: 20 items (20.0%)');
      expect(warmBar.getAttribute('title')).toBe('WARM: 50 items (50.0%)');
      expect(coldBar.getAttribute('title')).toBe('COLD: 30 items (30.0%)');
    });
  });

  describe('Tier Counts Display', () => {
    it('test_displays_hot_tier_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT
      expect(screen.getByText(/HOT: 20 \(20\.0%\)/)).toBeInTheDocument();
    });

    it('test_displays_warm_tier_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT
      expect(screen.getByText(/WARM: 50 \(50\.0%\)/)).toBeInTheDocument();
    });

    it('test_displays_cold_tier_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT
      expect(screen.getByText(/COLD: 30 \(30\.0%\)/)).toBeInTheDocument();
    });

    it('test_percentage_formatting_one_decimal_place', () => {
      // ARRANGE: Stats with non-round percentages
      const stats: ContextStats = {
        ...mockStats,
        hot_count: 33,
        warm_count: 33,
        cold_count: 34,
        total_count: 100,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: Percentages shown with 1 decimal place
      expect(screen.getByText(/HOT: 33 \(33\.0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/WARM: 33 \(33\.0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/COLD: 34 \(34\.0%\)/)).toBeInTheDocument();
    });

    it('test_handles_decimal_percentages', () => {
      // ARRANGE: 7 items total
      const stats: ContextStats = {
        ...mockStats,
        hot_count: 2,
        warm_count: 3,
        cold_count: 2,
        total_count: 7,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: Percentages calculated correctly (2/7 = 28.6%, 3/7 = 42.9%)
      expect(screen.getByText(/HOT: 2 \(28\.6%\)/)).toBeInTheDocument();
      expect(screen.getByText(/WARM: 3 \(42\.9%\)/)).toBeInTheDocument();
      expect(screen.getByText(/COLD: 2 \(28\.6%\)/)).toBeInTheDocument();
    });
  });

  describe('Legend Display', () => {
    it('test_legend_shows_all_tiers', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Legend items are present
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotLegend = container!.querySelector('.legend-item.hot');
      const warmLegend = container!.querySelector('.legend-item.warm');
      const coldLegend = container!.querySelector('.legend-item.cold');

      expect(hotLegend).toBeInTheDocument();
      expect(warmLegend).toBeInTheDocument();
      expect(coldLegend).toBeInTheDocument();
    });

    it('test_legend_color_indicators_present', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Color indicators (spans) are present in legend
      const container = screen.getByText('Tier Distribution').parentElement;
      const colorSpans = container!.querySelectorAll('.legend-color');

      expect(colorSpans.length).toBe(3); // One for each tier
    });

    it('test_legend_labels_match_tier_data', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Legend labels show correct text
      const container = screen.getByText('Tier Distribution').parentElement;
      const legendLabels = container!.querySelectorAll('.legend-label');

      expect(legendLabels[0].textContent).toBe('HOT: 20 (20.0%)');
      expect(legendLabels[1].textContent).toBe('WARM: 50 (50.0%)');
      expect(legendLabels[2].textContent).toBe('COLD: 30 (30.0%)');
    });
  });

  describe('Token Distribution', () => {
    it('test_displays_token_breakdown_section', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT
      expect(screen.getByText('Token Distribution:')).toBeInTheDocument();
    });

    it('test_displays_hot_token_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: HOT tokens with percentage (15,000 / 50,000 = 30%)
      expect(screen.getByText(/HOT: 15,000 tokens \(30\.0%\)/)).toBeInTheDocument();
    });

    it('test_displays_warm_token_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: WARM tokens with percentage (25,000 / 50,000 = 50%)
      expect(screen.getByText(/WARM: 25,000 tokens \(50\.0%\)/)).toBeInTheDocument();
    });

    it('test_displays_cold_token_count', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: COLD tokens with percentage (10,000 / 50,000 = 20%)
      expect(screen.getByText(/COLD: 10,000 tokens \(20\.0%\)/)).toBeInTheDocument();
    });

    it('test_token_counts_formatted_with_commas', () => {
      // ARRANGE: Large token counts
      const stats: ContextStats = {
        ...mockStats,
        hot_tokens: 150000,
        warm_tokens: 250000,
        cold_tokens: 100000,
        total_tokens: 500000,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: Numbers formatted with commas
      expect(screen.getByText(/150,000 tokens/)).toBeInTheDocument();
      expect(screen.getByText(/250,000 tokens/)).toBeInTheDocument();
      expect(screen.getByText(/100,000 tokens/)).toBeInTheDocument();
    });

    it('test_token_percentages_calculated_correctly', () => {
      // ARRANGE: Non-round token percentages
      const stats: ContextStats = {
        ...mockStats,
        hot_tokens: 12345,
        warm_tokens: 23456,
        cold_tokens: 9876,
        total_tokens: 45677,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: Percentages calculated correctly (1 decimal place)
      // 12345 / 45677 = 27.0%
      // 23456 / 45677 = 51.4%
      // 9876 / 45677 = 21.6%
      expect(screen.getByText(/HOT: 12,345 tokens \(27\.0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/WARM: 23,456 tokens \(51\.4%\)/)).toBeInTheDocument();
      expect(screen.getByText(/COLD: 9,876 tokens \(21\.6%\)/)).toBeInTheDocument();
    });

    it('test_token_list_has_tier_specific_classes', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Token list items have tier classes for styling
      const container = screen.getByText('Tier Distribution').parentElement;
      const tokenBreakdown = container!.querySelector('.token-breakdown');
      const tokenList = tokenBreakdown!.querySelector('ul');

      const hotItem = tokenList!.querySelector('li.hot');
      const warmItem = tokenList!.querySelector('li.warm');
      const coldItem = tokenList!.querySelector('li.cold');

      expect(hotItem).toBeInTheDocument();
      expect(warmItem).toBeInTheDocument();
      expect(coldItem).toBeInTheDocument();
    });
  });

  describe('Empty/Zero Data Handling', () => {
    it('test_shows_empty_state_when_no_items', () => {
      // ARRANGE: Zero items
      const emptyStats: ContextStats = {
        ...mockStats,
        hot_count: 0,
        warm_count: 0,
        cold_count: 0,
        total_count: 0,
        hot_tokens: 0,
        warm_tokens: 0,
        cold_tokens: 0,
        total_tokens: 0,
      };

      // ACT
      render(<ContextTierChart stats={emptyStats} />);

      // ASSERT
      expect(screen.getByText('No context items')).toBeInTheDocument();
    });

    it('test_no_chart_bars_when_empty', () => {
      // ARRANGE
      const emptyStats: ContextStats = {
        ...mockStats,
        hot_count: 0,
        warm_count: 0,
        cold_count: 0,
        total_count: 0,
      };

      // ACT
      render(<ContextTierChart stats={emptyStats} />);

      // ASSERT: No chart bars rendered
      const container = screen.getByText('Tier Distribution').parentElement;
      const chartBars = container!.querySelectorAll('.chart-bar');

      expect(chartBars.length).toBe(0);
    });

    it('test_no_legend_when_empty', () => {
      // ARRANGE
      const emptyStats: ContextStats = {
        ...mockStats,
        hot_count: 0,
        warm_count: 0,
        cold_count: 0,
        total_count: 0,
      };

      // ACT
      render(<ContextTierChart stats={emptyStats} />);

      // ASSERT: No legend rendered
      const container = screen.getByText('Tier Distribution').parentElement;
      const legend = container!.querySelector('.chart-legend');

      expect(legend).not.toBeInTheDocument();
    });

    it('test_zero_percentage_when_zero_tokens', () => {
      // ARRANGE: Zero tokens
      const zeroTokenStats: ContextStats = {
        ...mockStats,
        hot_tokens: 0,
        warm_tokens: 0,
        cold_tokens: 0,
        total_tokens: 0,
      };

      // ACT
      render(<ContextTierChart stats={zeroTokenStats} />);

      // ASSERT: Token percentages show 0%
      expect(screen.getByText(/HOT: 0 tokens \(0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/WARM: 0 tokens \(0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/COLD: 0 tokens \(0%\)/)).toBeInTheDocument();
    });

    it('test_handles_zero_hot_count', () => {
      // ARRANGE: No HOT items
      const stats: ContextStats = {
        ...mockStats,
        hot_count: 0,
        hot_tokens: 0,
        warm_count: 60,
        cold_count: 40,
        total_count: 100,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: No HOT bar rendered, but WARM and COLD are present
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot');
      const warmBar = container!.querySelector('.chart-bar.warm');
      const coldBar = container!.querySelector('.chart-bar.cold');

      expect(hotBar).not.toBeInTheDocument();
      expect(warmBar).toBeInTheDocument();
      expect(coldBar).toBeInTheDocument();

      // Legend still shows all tiers including HOT with 0
      expect(screen.getByText(/HOT: 0 \(0\.0%\)/)).toBeInTheDocument();
    });

    it('test_handles_zero_warm_count', () => {
      // ARRANGE: No WARM items
      const stats: ContextStats = {
        ...mockStats,
        hot_count: 40,
        warm_count: 0,
        warm_tokens: 0,
        cold_count: 60,
        total_count: 100,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: No WARM bar rendered
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot');
      const warmBar = container!.querySelector('.chart-bar.warm');
      const coldBar = container!.querySelector('.chart-bar.cold');

      expect(hotBar).toBeInTheDocument();
      expect(warmBar).not.toBeInTheDocument();
      expect(coldBar).toBeInTheDocument();

      // Legend shows WARM with 0
      expect(screen.getByText(/WARM: 0 \(0\.0%\)/)).toBeInTheDocument();
    });

    it('test_handles_zero_cold_count', () => {
      // ARRANGE: No COLD items
      const stats: ContextStats = {
        ...mockStats,
        hot_count: 50,
        warm_count: 50,
        cold_count: 0,
        cold_tokens: 0,
        total_count: 100,
      };

      // ACT
      render(<ContextTierChart stats={stats} />);

      // ASSERT: No COLD bar rendered
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot');
      const warmBar = container!.querySelector('.chart-bar.warm');
      const coldBar = container!.querySelector('.chart-bar.cold');

      expect(hotBar).toBeInTheDocument();
      expect(warmBar).toBeInTheDocument();
      expect(coldBar).not.toBeInTheDocument();

      // Legend shows COLD with 0
      expect(screen.getByText(/COLD: 0 \(0\.0%\)/)).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('test_handles_single_item', () => {
      // ARRANGE: Only 1 HOT item
      const singleItemStats: ContextStats = {
        ...mockStats,
        hot_count: 1,
        warm_count: 0,
        cold_count: 0,
        total_count: 1,
        hot_tokens: 100,
        warm_tokens: 0,
        cold_tokens: 0,
        total_tokens: 100,
      };

      // ACT
      render(<ContextTierChart stats={singleItemStats} />);

      // ASSERT: HOT bar is 100% width
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot') as HTMLElement;

      expect(hotBar.style.width).toBe('100%');
      expect(screen.getByText(/HOT: 1 \(100\.0%\)/)).toBeInTheDocument();
    });

    it('test_handles_very_large_counts', () => {
      // ARRANGE: Large numbers
      const largeStats: ContextStats = {
        ...mockStats,
        hot_count: 10000,
        warm_count: 25000,
        cold_count: 15000,
        total_count: 50000,
        hot_tokens: 5000000,
        warm_tokens: 12500000,
        cold_tokens: 7500000,
        total_tokens: 25000000,
      };

      // ACT
      render(<ContextTierChart stats={largeStats} />);

      // ASSERT: Numbers formatted correctly with commas
      expect(screen.getByText(/HOT: 10000 \(20\.0%\)/)).toBeInTheDocument();
      expect(screen.getByText(/5,000,000 tokens/)).toBeInTheDocument();
    });

    it('test_handles_100_percent_hot', () => {
      // ARRANGE: All items are HOT
      const allHotStats: ContextStats = {
        ...mockStats,
        hot_count: 100,
        warm_count: 0,
        cold_count: 0,
        total_count: 100,
      };

      // ACT
      render(<ContextTierChart stats={allHotStats} />);

      // ASSERT
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot') as HTMLElement;

      expect(hotBar.style.width).toBe('100%');
      expect(screen.getByText(/HOT: 100 \(100\.0%\)/)).toBeInTheDocument();
    });

    it('test_handles_fractional_item_counts', () => {
      // ARRANGE: Edge case - stats shouldn't have fractional counts, but test robustness
      const fractionalStats: ContextStats = {
        ...mockStats,
        hot_count: 3,
        warm_count: 3,
        cold_count: 3,
        total_count: 9, // Results in 33.33% each
      };

      // ACT
      render(<ContextTierChart stats={fractionalStats} />);

      // ASSERT: Percentages rounded correctly
      expect(screen.getByText(/HOT: 3 \(33\.3%\)/)).toBeInTheDocument();
      expect(screen.getByText(/WARM: 3 \(33\.3%\)/)).toBeInTheDocument();
      expect(screen.getByText(/COLD: 3 \(33\.3%\)/)).toBeInTheDocument();
    });
  });

  describe('Color Coding', () => {
    it('test_hot_tier_uses_hot_class', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: HOT elements have 'hot' class
      const container = screen.getByText('Tier Distribution').parentElement;
      const hotBar = container!.querySelector('.chart-bar.hot');
      const hotLegend = container!.querySelector('.legend-item.hot');
      const hotToken = container!.querySelector('li.hot');

      expect(hotBar).toBeInTheDocument();
      expect(hotLegend).toBeInTheDocument();
      expect(hotToken).toBeInTheDocument();
    });

    it('test_warm_tier_uses_warm_class', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: WARM elements have 'warm' class
      const container = screen.getByText('Tier Distribution').parentElement;
      const warmBar = container!.querySelector('.chart-bar.warm');
      const warmLegend = container!.querySelector('.legend-item.warm');
      const warmToken = container!.querySelector('li.warm');

      expect(warmBar).toBeInTheDocument();
      expect(warmLegend).toBeInTheDocument();
      expect(warmToken).toBeInTheDocument();
    });

    it('test_cold_tier_uses_cold_class', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: COLD elements have 'cold' class
      const container = screen.getByText('Tier Distribution').parentElement;
      const coldBar = container!.querySelector('.chart-bar.cold');
      const coldLegend = container!.querySelector('.legend-item.cold');
      const coldToken = container!.querySelector('li.cold');

      expect(coldBar).toBeInTheDocument();
      expect(coldLegend).toBeInTheDocument();
      expect(coldToken).toBeInTheDocument();
    });
  });

  describe('Component Structure', () => {
    it('test_has_correct_root_class', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Root element has correct class
      const container = screen.getByText('Tier Distribution').parentElement;
      expect(container).toHaveClass('context-tier-chart');
    });

    it('test_chart_bar_container_exists', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Chart bar container present
      const container = screen.getByText('Tier Distribution').parentElement;
      const barContainer = container!.querySelector('.chart-bar-container');

      expect(barContainer).toBeInTheDocument();
    });

    it('test_token_breakdown_section_exists', () => {
      // ACT
      render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Token breakdown section present
      const container = screen.getByText('Tier Distribution').parentElement;
      const tokenBreakdown = container!.querySelector('.token-breakdown');

      expect(tokenBreakdown).toBeInTheDocument();
    });

    it('test_renders_as_single_component', () => {
      // ACT
      const { container } = render(<ContextTierChart stats={mockStats} />);

      // ASSERT: Only one root element
      const chartElements = container.querySelectorAll('.context-tier-chart');
      expect(chartElements.length).toBe(1);
    });
  });
});
