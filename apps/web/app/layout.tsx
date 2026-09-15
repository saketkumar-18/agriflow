import type { Metadata, Viewport } from "next";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/auth";
import { SwRegister } from "@/components/sw-register";

export const metadata: Metadata = {
  title: "AgriFlow — Smart irrigation advice",
  description:
    "Mobile-first decision support for Indian farmers: know if your field needs irrigation, in seconds.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon-192.png" },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "AgriFlow",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#065f46",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <I18nProvider>
          <AuthProvider>
            <SwRegister />
            {children}
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
