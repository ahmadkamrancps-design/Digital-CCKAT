import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthProvider } from '../src/features/auth/AuthProvider';

const dialogPrototype = HTMLDialogElement.prototype;
const originalShowModal = Object.getOwnPropertyDescriptor(dialogPrototype, 'showModal');
const originalClose = Object.getOwnPropertyDescriptor(dialogPrototype, 'close');

// jsdom has no native modal-dialog methods; browsers provide focus containment.
beforeAll(() => {
  Object.defineProperty(dialogPrototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(dialogPrototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); } });
});
afterAll(() => {
  if (originalShowModal) Object.defineProperty(dialogPrototype, 'showModal', originalShowModal);
  else Reflect.deleteProperty(dialogPrototype, 'showModal');
  if (originalClose) Object.defineProperty(dialogPrototype, 'close', originalClose);
  else Reflect.deleteProperty(dialogPrototype, 'close');
});
beforeEach(() => {
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_ENABLE_UI_PREVIEW', 'true');
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('No backend in preview')));
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function renderExam(path = '/exam') {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
}

describe('exam interface preview', () => {
  it('keeps MCQ selections and review flags while navigating, and clears only the answer', async () => {
    renderExam();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /^Question 2,/ }));
    await userEvent.click(screen.getByRole('radio', { name: 'destruction' }));
    await userEvent.click(screen.getByRole('button', { name: 'Mark for Review' }));
    expect(screen.getByRole('button', { name: /^Question 2, answered, marked for review/ })).toHaveAttribute('aria-current', 'step');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(screen.getByRole('radio', { name: 'destruction' })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Mark for Review' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Clear Answer' }));
    expect(screen.getByRole('radio', { name: 'destruction' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: /^Question 2, unanswered, marked for review/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^Question 30,/ }));
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('preserves short answers and question positions separately when switching subjects', async () => {
    renderExam();
    const selector = screen.getByRole('combobox', { name: 'Preview subject' });
    await userEvent.selectOptions(selector, 'sample-mathematics');
    await userEvent.click(screen.getByRole('button', { name: /^Question 4,/ }));
    expect(screen.getByText('3(x + 5) = 24')).toBeInTheDocument();
    const input = screen.getByRole('textbox', { name: 'Your answer' });
    expect(input).toHaveAttribute('inputmode', 'decimal');
    await userEvent.type(input, '3');
    await userEvent.selectOptions(selector, 'sample-english');
    expect(screen.getByRole('heading', { name: 'Question 1 of 30' })).toBeInTheDocument();
    await userEvent.selectOptions(selector, 'sample-mathematics');
    expect(screen.getByRole('heading', { name: 'Question 4 of 30' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toHaveValue('3');
    expect(screen.getByRole('timer')).toHaveTextContent('60:00');
    expect(screen.getByText('Preview timer · paused')).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('supports Urdu Unicode input with local right-to-left direction', async () => {
    renderExam('/exam?subject=sample-urdu');
    const input = screen.getByRole('textbox', { name: 'Your answer' });
    expect(input).toHaveAttribute('dir', 'rtl');
    await userEvent.type(input, 'حسین');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toHaveValue('حسین');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('requires confirmation to finish a preview, never submits to the backend, and permits restart', async () => {
    renderExam();
    await userEvent.click(screen.getByRole('radio', { name: 'beautiful' }));
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
    expect(screen.getByRole('dialog', { name: 'Finish English preview?' })).toHaveTextContent('29 unanswered questions');
    await userEvent.click(screen.getByRole('button', { name: 'Keep reviewing' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'beautiful' })).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
    await userEvent.click(screen.getByRole('button', { name: 'Finish preview' }));
    expect(screen.getByRole('heading', { name: 'Test Submitted Successfully!' })).toBeInTheDocument();
    expect(screen.getByText(/no test has been submitted to CCK/)).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Restart subject preview' }));
    expect(screen.getByRole('radio', { name: 'beautiful' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Finish' })).toBeEnabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('continues through configured subjects after finishing and returns to the dashboard after the last', async () => {
    renderExam();
    for (const nextName of ['Mathematics', 'Urdu']) {
      await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
      await userEvent.click(screen.getByRole('button', { name: 'Finish preview' }));
      expect(screen.getByText('30', { selector: 'dd' })).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: `Continue to ${nextName}` }));
      expect(screen.getByRole('combobox', { name: 'Preview subject' })).toHaveDisplayValue(nextName);
    }
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }));
    await userEvent.click(screen.getByRole('button', { name: 'Finish preview' }));
    expect(screen.queryByRole('button', { name: /^Continue to/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Return to dashboard' }));
    expect(screen.getByRole('heading', { name: 'Welcome, Ahmad Kamran.' })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows a clearly labeled submission design on direct access, including an unknown subject fallback', async () => {
    renderExam('/submission?subject=unknown');
    expect(screen.getByText('English', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('Sample Submission Time')).toBeInTheDocument();
    expect(screen.getByText(/no test has been submitted to CCK/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Continue to Mathematics' }));
    expect(screen.getByRole('combobox', { name: 'Preview subject' })).toHaveDisplayValue('Mathematics');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('resets sample responses on remount without claiming persistence', async () => {
    const view = renderExam();
    await userEvent.click(screen.getByRole('radio', { name: 'beautiful' }));
    view.unmount();
    renderExam();
    expect(screen.getByRole('radio', { name: 'beautiful' })).not.toBeChecked();
    expect(screen.getByText(/Preview responses stay on this page only/)).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});
