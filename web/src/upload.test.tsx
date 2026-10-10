import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { DatabaseUpload } from './components/DatabaseUpload';

function renderUpload() {
  render(<QueryClientProvider client={new QueryClient()}><DatabaseUpload /></QueryClientProvider>);
  return screen.getByLabelText('Database file') as HTMLInputElement;
}

describe('DatabaseUpload', () => {
  it('rejects files over the size limit before uploading', () => {
    const send = vi.spyOn(XMLHttpRequest.prototype, 'send');
    const input = renderUpload();
    const file = new File(['x'], 'huge.db');
    Object.defineProperty(file, 'size', { value: 300 * 1024 * 1024 });
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByRole('alert').textContent).toMatch(/larger than the 200 MB limit/);
    expect(send).not.toHaveBeenCalled();
  });

  it('only offers SQLite file types in the picker', () => {
    expect(renderUpload().accept).toBe('.db,.sqlite,.sqlite3,.db3');
  });
});
