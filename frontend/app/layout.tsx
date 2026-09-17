import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Connact.ai",
  icons: { icon: "/connact-icon.svg" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              'try{const s=localStorage.getItem("connectai-theme");document.documentElement.dataset.theme=s==="light"||s==="dark"?s:matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}catch{document.documentElement.dataset.theme="light"}',
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
