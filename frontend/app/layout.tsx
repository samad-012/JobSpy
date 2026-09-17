import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JobSpy Search",
  description: "Search current job listings across supported sources.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
