import type { Metadata, Viewport } from "next";
import { Geist, IBM_Plex_Mono, Instrument_Serif } from "next/font/google";
import { Toaster } from "sonner";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
const instrument = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: { default: "Factory · AI Content Studio", template: "%s · Factory" },
  description:
    "Operational control room for an autonomous, multi-agent YouTube content factory.",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${plexMono.variable} ${instrument.variable} h-full`}
    >
      <body className="min-h-full bg-background text-foreground font-sans antialiased">
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: "!rounded-none !border !border-ink !bg-white !text-ink !font-mono !text-xs",
          }}
        />
      </body>
    </html>
  );
}
