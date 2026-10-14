import "@fontsource/big-shoulders-display/latin-700";
import "@fontsource/big-shoulders-display/latin-900";
import "@fontsource/instrument-sans/latin-400";
import "@fontsource/instrument-sans/latin-600";
import "./globals.css";

export const metadata = { title: "Fachada — panel de administración", description: "Panel para administrar edificios: accesos, patentes, visitas y cobranza." };
export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }) {
  return (<html lang="es"><body>{children}</body></html>);
}
