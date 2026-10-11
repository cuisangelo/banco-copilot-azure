import type { Metadata } from "next";
import { Montserrat, Source_Sans_3 } from "next/font/google";
import { TopBar } from "@/components/TopBar";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const montserrat = Montserrat({ variable: "--font-montserrat", subsets: ["latin"], weight: ["600", "700", "800"] });
const sourceSans = Source_Sans_3({ variable: "--font-source-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Copiloto de atención · Banco Austral",
  description: "Respuestas con fuente para asesores de Banco Austral.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${montserrat.variable} ${sourceSans.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <SessionProvider>
          <TopBar />
          {children}
        </SessionProvider>
      </body>
    </html>
  );
}
