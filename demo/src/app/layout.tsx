import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIST — Agentic Infrastructure Stress Test",
  description:
    "Why agents fail silently on degraded data, and what a pipeline score can " +
    "tell you before you deploy one. Every figure exported from 248 benchmark runs.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
