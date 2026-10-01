import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Runveil | Local approvals",
  description: "A production-style AI agent runtime, under development.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
