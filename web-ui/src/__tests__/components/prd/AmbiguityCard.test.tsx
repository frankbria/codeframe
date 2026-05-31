import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AmbiguityCard } from '@/components/prd/AmbiguityCard';
import type { StressTestAmbiguity } from '@/types';

function ambiguity(
  overrides: Partial<StressTestAmbiguity> = {}
): StressTestAmbiguity {
  return {
    id: 'amb-1',
    label: 'AUTH SCOPE',
    source_node_title: 'User Authentication',
    questions: ['Email/password or OAuth?', 'JWT or sessions?'],
    recommendation: 'Add an Authentication section',
    severity: 'blocking',
    resolved_answer: null,
    ...overrides,
  };
}

describe('AmbiguityCard', () => {
  it('renders label, questions, and recommendation', () => {
    render(
      <AmbiguityCard ambiguity={ambiguity()} answer="" onChange={jest.fn()} />
    );

    expect(screen.getByText('AUTH SCOPE')).toBeInTheDocument();
    expect(screen.getByText('Email/password or OAuth?')).toBeInTheDocument();
    expect(screen.getByText('JWT or sessions?')).toBeInTheDocument();
    expect(
      screen.getByText(/Add an Authentication section/)
    ).toBeInTheDocument();
    expect(screen.getByText(/From: User Authentication/)).toBeInTheDocument();
  });

  it('shows a Blocking badge for blocking severity', () => {
    render(
      <AmbiguityCard
        ambiguity={ambiguity({ severity: 'blocking' })}
        answer=""
        onChange={jest.fn()}
      />
    );
    expect(screen.getByText('Blocking')).toBeInTheDocument();
  });

  it('shows a Warning badge for warning severity', () => {
    render(
      <AmbiguityCard
        ambiguity={ambiguity({ severity: 'warning' })}
        answer=""
        onChange={jest.fn()}
      />
    );
    expect(screen.getByText('Warning')).toBeInTheDocument();
  });

  it('reflects the controlled answer value', () => {
    render(
      <AmbiguityCard
        ambiguity={ambiguity()}
        answer="Email/password"
        onChange={jest.fn()}
      />
    );
    expect(
      screen.getByRole('textbox', { name: /Answer for AUTH SCOPE/i })
    ).toHaveValue('Email/password');
  });

  it('calls onChange with the ambiguity id when typing', async () => {
    const onChange = jest.fn();
    render(
      <AmbiguityCard ambiguity={ambiguity()} answer="" onChange={onChange} />
    );
    await userEvent.type(
      screen.getByRole('textbox', { name: /Answer for AUTH SCOPE/i }),
      'X'
    );
    expect(onChange).toHaveBeenCalledWith('amb-1', 'X');
  });
});
