from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable
from collections import defaultdict

from logic.modelos import Movimiento, Match


@dataclass(frozen=True)
class Parametros:
    tolerancia_importe: float = 0.0
    tolerancia_dias: int = 0
    permitir_conciliacion_grupal: bool = False
    permitir_grupos_fuera_de_fecha: bool = False


def _nums(texto: str) -> set[str]:
    """Extrae todos los números de un texto como strings."""
    import re
    return set(re.findall(r"\d+", texto or ""))


def _key_base(m: Movimiento) -> tuple:
    """Clave base para intentar aparear movimientos exactos."""
    return (m.fecha, round(m.importe, 2))


def conciliar(
    banco: list[Movimiento],
    interno: list[Movimiento],
    params: Parametros = Parametros(),
) -> tuple[list[Match], list[Movimiento], list[Movimiento]]:
    matches: list[Match] = []
    consumidos_b, consumidos_i = set(), set()

    # Índice por clave base (fecha+importe)
    idx_i = {_key_base(m): m for m in interno}
    keys_comunes = set(_key_base(m) for m in banco) & set(idx_i.keys())

    # --- Conciliación exacta ---
    for b in banco:
        kb = _key_base(b)
        if kb in idx_i:
            i = idx_i[kb]
            nb, ni = _nums(b.descripcion), _nums(i.descripcion)
            if nb & ni:
                estado, corr = "Conciliado exacto", "Coincidencia con números"
            else:
                estado, corr = "Conciliado exacto", "Coincidencia exacta por fecha/importe"
            matches.append(Match(
                fecha_banco=b.fecha,
                importe_banco=b.importe,
                desc_banco=b.descripcion,
                fecha_interno=i.fecha,
                importe_interno=i.importe,
                desc_interno=i.descripcion,
                estado=estado,
                correccion_sugerida=corr,
            ))
            consumidos_b.add(id(b))
            consumidos_i.add(id(i))

    # --- Pendientes ---
    pendientes_b = [m for m in banco if id(m) not in consumidos_b and _key_base(m) not in keys_comunes]
    pendientes_i = [m for m in interno if id(m) not in consumidos_i and _key_base(m) not in keys_comunes]

    # --- Sugerencias por tolerancia ---
    if params.tolerancia_importe > 0 or params.tolerancia_dias > 0:
        matches.extend(
            sugerencias_por_tolerancia(pendientes_b, pendientes_i,
                                       params.tolerancia_importe,
                                       params.tolerancia_dias)
        )

    # --- Conciliación grupal ---
    if params.permitir_conciliacion_grupal:
        matches.extend(
            conciliacion_grupal(
                pendientes_b, pendientes_i,
                params.tolerancia_importe,
                params.tolerancia_dias,
                params.permitir_grupos_fuera_de_fecha
            )
        )

    # --- Recalcular pendientes después de matches adicionales ---
    usados_b = {(m.fecha_banco, m.importe_banco, m.desc_banco) for m in matches}
    usados_i = {(m.fecha_interno, m.importe_interno, m.desc_interno) for m in matches}

    pendientes_b = [m for m in pendientes_b if (m.fecha, m.importe, m.descripcion) not in usados_b]
    pendientes_i = [m for m in pendientes_i if (m.fecha, m.importe, m.descripcion) not in usados_i]

    return matches, pendientes_b, pendientes_i


def sugerencias_por_tolerancia(
    pendientes_b: Iterable[Movimiento],
    pendientes_i: Iterable[Movimiento],
    tolerancia_importe: float,
    tolerancia_dias: int,
) -> list[Match]:
    """Sugiere coincidencias basadas en tolerancias de fecha e importe."""
    idx_i_fecha = defaultdict(list)
    for m in pendientes_i:
        idx_i_fecha[m.fecha].append(m)

    out: list[Match] = []
    for b in pendientes_b:
        fmin = b.fecha - timedelta(days=tolerancia_dias)
        fmax = b.fecha + timedelta(days=tolerancia_dias)

        candidatos: list[Movimiento] = []
        for d in (fmin + timedelta(days=k) for k in range((fmax - fmin).days + 1)):
            candidatos.extend(idx_i_fecha.get(d, []))

        # Ventana de importes
        candidatos = [c for c in candidatos if abs(c.importe - b.importe) <= tolerancia_importe]

        for i in candidatos:
            nb, ni = _nums(b.descripcion), _nums(i.descripcion)
            if nb & ni:
                estado, corr = "Sugerido (descripción)", "Coincidencia por número en descripción"
            else:
                estado, corr = "Sugerido (tolerancias)", "Revisar manual (dentro de tolerancias)"
            out.append(Match(
                fecha_banco=b.fecha,
                importe_banco=b.importe,
                desc_banco=b.descripcion,
                fecha_interno=i.fecha,
                importe_interno=i.importe,
                desc_interno=i.descripcion,
                estado=estado,
                correccion_sugerida=corr,
            ))
    return out


def conciliacion_grupal(
    pendientes_b: Iterable[Movimiento],
    pendientes_i: Iterable[Movimiento],
    tolerancia_importe: float,
    tolerancia_dias: int,
    permitir_fuera_fecha: bool,
) -> list[Match]:
    """Conciliación grupal: compara sumas de movimientos de un mismo día contra sumas del otro origen."""
    out: list[Match] = []

    # Agrupar por fecha
    grupos_b = defaultdict(list)
    grupos_i = defaultdict(list)
    for m in pendientes_b:
        grupos_b[m.fecha].append(m)
    for m in pendientes_i:
        grupos_i[m.fecha].append(m)

    for fb, grupo_b in grupos_b.items():
        suma_b = sum(m.importe for m in grupo_b)

        for fi, grupo_i in grupos_i.items():
            suma_i = sum(m.importe for m in grupo_i)

            # Condición de fechas
            fechas_ok = (fb == fi) or (
                permitir_fuera_fecha and abs((fb - fi).days) <= tolerancia_dias
            )

            # Condición de importes
            importes_ok = abs(suma_b - suma_i) <= tolerancia_importe

            if fechas_ok and importes_ok:
                desc_b = "; ".join(m.descripcion for m in grupo_b[:3])
                desc_i = "; ".join(m.descripcion for m in grupo_i[:3])

                out.append(Match(
                    fecha_banco=fb,
                    importe_banco=suma_b,
                    desc_banco=f"[Grupo {len(grupo_b)} movs] {desc_b}...",
                    fecha_interno=fi,
                    importe_interno=suma_i,
                    desc_interno=f"[Grupo {len(grupo_i)} movs] {desc_i}...",
                    estado="Sugerido (grupal)",
                    correccion_sugerida="Revisar suma de movimientos (grupo)",
                ))
    return out
