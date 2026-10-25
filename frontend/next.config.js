const api = process.env.NEXT_PUBLIC_API_URL || "";
let origenApi = "";
try { origenApi = api ? new URL(api).origin : ""; } catch { /* URL inválida: sólo mismo origen */ }

// Next inyecta scripts en línea para hidratar, por eso 'unsafe-inline' en script-src; el resto es estricto.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${origenApi}`.trim(),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

module.exports = {
  // En Docker (NEXT_OUTPUT=standalone) el panel sale como un servidor mínimo; en desarrollo y E2E se usa `next start`.
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" } : {}),
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: csp },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ],
    }];
  },
};
