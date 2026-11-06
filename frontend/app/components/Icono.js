// Iconos de trazo único (24x24, 1.75 px, esquinas redondeadas), dibujados aquí para no depender de emojis.
const TRAZOS = {
  paquete: "M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5v-9ZM3.5 7.5 12 12m0 0 8.5-4.5M12 12v9M7.8 5.3l8.5 4.5",
  fijar: "M9 3h6l-1 6 3 3H7l3-3-1-6ZM12 12v8",
  ok: "m5 12.5 4.5 4.5L19 7.5",
  alerta: "M12 4 3 20h18L12 4ZM12 10v4.5M12 17.2v.1",
  cerrar: "M6 6l12 12M18 6 6 18",
  whatsapp: "M4 20l1.3-4.2A8 8 0 1 1 8.3 18.8L4 20Zm5-11c.3 2.8 3 5.5 6 6l1.2-1.4-2-1-1 .7c-.9-.4-1.9-1.4-2.3-2.3l.7-1-1-2L9 9Z",
};

export default function Icono({ n, size = 18, titulo }) {
  return (
    <svg className="icono" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" role={titulo ? "img" : undefined}
      aria-label={titulo} aria-hidden={titulo ? undefined : true}>
      <path d={TRAZOS[n]} />
    </svg>
  );
}
