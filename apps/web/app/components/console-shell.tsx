import type { ReactNode } from "react";

export default function ConsoleShell({
  active,
  children,
  operator = false,
}: {
  active: string;
  children: ReactNode;
  operator?: boolean;
}) {
  return (
    <>
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <header className="console-header">
        <div className="header-inner">
          {/* Full document navigation clears operator credentials and outstanding requests. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a className="wordmark" href="/">
            Runveil<span> / execution console</span>
          </a>
          <span className="environment">
            {operator ? "Local operator" : "Recorded showcase"}
          </span>
        </div>
        <nav className="console-nav" aria-label="Main navigation">
          {[
            ["/", "Overview"],
            ["/runs", "Recorded runs"],
            ["/traces", "Live trace"],
            ["/approvals", "Local approvals"],
          ].map(([href, label]) => (
            // Full navigation is intentional across the separate credential surfaces.
            <a
              key={href}
              href={href}
              aria-current={active === label ? "page" : undefined}
            >
              {label}
            </a>
          ))}
        </nav>
      </header>
      <main id="content" className="console-main">
        {children}
      </main>
      <footer className="console-footer">
        <span>Runveil · Inspect. Review. Verify.</span>
        <span>
          {operator
            ? "Credentials stay in this page’s memory."
            : "Public fixture evidence · Scripted provider · No live execution"}
        </span>
      </footer>
    </>
  );
}
