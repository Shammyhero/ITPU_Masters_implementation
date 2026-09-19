import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIRS — is your data pipeline ready for an agent?",
  description:
    "Score a data pipeline's readiness for an AI agent from a sample of its records, " +
    "and see the evidence that the score means something.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav" aria-label="Site">
          <div className="topnav-inner">
            <Link href="/" className="brand">AIRS</Link>
            <Link href="/">Ask your pipeline</Link>
            <Link href="/check/">Check my pipeline</Link>
            <Link href="/evidence/">Why trust the score</Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
