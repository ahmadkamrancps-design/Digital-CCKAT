import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import CCKLogo from './CCKLogo';

export function Layout({ children }: { children: ReactNode }) {
  return <>
    <a className="skip-link" href="#main">Skip to main content</a>
    <header className="site-header">
      <Link to="/" className="brand" aria-label="CCK Digital Entry Test home">
        <CCKLogo />
      </Link>
      <span className="portal-label">Candidate portal</span>
    </header>
    <main id="main" tabIndex={-1}>{children}</main>
    <footer>Cadet College Kohat · Digital Entry Test</footer>
  </>;
}
