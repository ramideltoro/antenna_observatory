import type { Metadata, Viewport } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'Antenna Observatory',
  applicationName: 'Antenna Observatory',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: '/favicon.svg',
    apple: '/icons/icon-192.png',
  },
  appleWebApp: {
    capable: true,
    title: 'Observatory',
    statusBarStyle: 'black-translucent',
  },
  description:
    'Local aircraft signals, receiver health, and feed observability.',
};
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#11150f',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
