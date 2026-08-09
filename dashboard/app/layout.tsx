import type { Metadata } from "next";
import { Geist_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import PwaRegister from "./components/PwaRegister";

const newsreader = Newsreader({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Incidents CAMTEL - Dashboard",
  description: "Historique des fiches d'incidents CAMTEL générées automatiquement",
  themeColor: "#faf7f0",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="fr"
      className={`${newsreader.variable} ${geistMono.variable}`}
    >
      <body>
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}