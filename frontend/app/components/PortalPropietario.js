"use client";
import { useState } from "react";
import MiDepto from "./MiDepto";

// Vista del administrador o conserje sobre el portal de un departamento: mismos datos reales que ve el residente.
export default function PortalPropietario({ data, api, deptoInicial }) {
  const unidades = [...data.unidades].sort((a, b) => a.numero.localeCompare(b.numero, "es", { numeric: true }));
  const [id, setId] = useState(deptoInicial || unidades[0]?.id);
  if (!unidades.length) return <p className="vacio">Este edificio aún no tiene departamentos cargados.</p>;
  return (
    <div className="seccion-vista">
      <div className="fila-form">
        <label>Departamento
          <select value={id} onChange={(e) => setId(Number(e.target.value))}>
            {unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}{u.deuda > 0 ? " · con saldo" : ""}</option>)}
          </select></label>
      </div>
      <MiDepto key={id} api={api} unidadId={id} embebido onSalir={() => {}} />
    </div>
  );
}
