import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Runveil | Execution console",
  description:
    "Inspect recorded coding-agent runs, exact proposals and validation evidence.",
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
