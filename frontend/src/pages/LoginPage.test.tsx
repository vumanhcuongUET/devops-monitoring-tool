import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const post = vi.fn();
vi.mock('../api/client', () => ({
  api: { post: (...args: unknown[]) => post(...args) },
  tokenManager: { setToken: vi.fn() },
}));

import LoginPage from './LoginPage';

describe('LoginPage', () => {
  it('stores token and calls onLogin on success', async () => {
    post.mockResolvedValue({ data: { access_token: 't', expires_in: 900, role: 'admin' } });
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    await userEvent.type(screen.getByLabelText(/username/i), 'carol');
    await userEvent.type(screen.getByLabelText(/password/i), 'pw');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(onLogin).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/auth/login', { username: 'carol', password: 'pw' });
  });

  it('shows an error on 401', async () => {
    post.mockRejectedValue({ response: { status: 401 } });
    render(<LoginPage onLogin={vi.fn()} />);

    await userEvent.type(screen.getByLabelText(/username/i), 'carol');
    await userEvent.type(screen.getByLabelText(/password/i), 'bad');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument()
    );
  });
});
