from __future__ import annotations

import math
import unicodedata
from numbers import Integral, Real

import pandas as pd

from logic.modelos import Movimiento, Origen


def _sanitize_header(value: str) -> str:
    lowered = str(value).lower()
    replacements = {
        "cr?dito": "credito",
        "crÃ©dito": "credito",
        "crÃ©ditos": "creditos",
        "cr�dito": "credito",
        "d?bito": "debito",
        "dÃ©bito": "debito",
        "dÃ©bitos": "debitos",
        "d�bito": "debito",
    }
    for wrong, corrected in replacements.items():
        if wrong in lowered:
            lowered = lowered.replace(wrong, corrected)
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def detectar_columnas(df: pd.DataFrame) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    cols = list(df.columns)
    lower = [str(c).lower() for c in cols]
    sanitized = [_sanitize_header(c) for c in cols]

    def pick(keywords):
        for kw in keywords:
            kw_lower = kw.lower()
            kw_sanitized = _sanitize_header(kw)
            for original, raw, clean in zip(cols, lower, sanitized):
                if (
                    kw_lower in raw
                    or kw_lower in clean
                    or kw_sanitized in raw
                    or kw_sanitized in clean
                ):
                    return original
        return None

    f = pick(["fecha"])  # Fecha
    i = pick(["importe", "monto"])  # Importe único
    d = pick(["debito", "salida"])  # Débito
    c = pick(["credito", "entrada"])  # Crédito
    desc = pick([
        "detalle", "descrip", "concepto", "leyenda", "observac",
        "referen", "glosa", "coment", "n�", "n°", "nro", "numero"
    ])
    return f, i, d, c, desc

def detectar_encabezado(df: pd.DataFrame, tope: int = 10) -> int:
    """
    Detecta la fila que más probablemente corresponde al encabezado de un Excel
    buscando coincidencias con palabras clave típicas (fecha, importe, débito, etc).

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame leído con header=None.
    tope : int, opcional
        Cantidad máxima de filas a analizar desde arriba, por defecto 10.

    Retorna
    -------
    int
        Índice de la fila que se usará como encabezado.
    """
    palabras = [
        "fecha", "importe", "monto",
        "debito", "débito",
        "credito", "crédito",
        "concepto", "desc", "detalle",
        "nro", "numero"
    ]
    fila_header, max_matches = 0, 0
    tope = min(tope, len(df))

    for i in range(tope):
        fila = df.iloc[i].astype(str).str.lower()
        matches = sum(any(p in val for p in palabras) for val in fila)
        if matches > max_matches:
            max_matches, fila_header = matches, i

    return fila_header

def limpiar_importe_serie(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str)
        .str.replace(r"[^0-9,.\-]", "", regex=True)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )


def calcular_importe_final(
    df: pd.DataFrame,
    col_importe: str | None,
    col_debito: str | None,
    col_credito: str | None
) -> pd.Series:
    if col_importe:
        return limpiar_importe_serie(df[col_importe]).round(2)
    if col_debito and col_credito:
        if col_debito == col_credito:
            return limpiar_importe_serie(df[col_debito]).round(2)
        deb = limpiar_importe_serie(df[col_debito]).fillna(0)
        cred = limpiar_importe_serie(df[col_credito]).fillna(0)
        return (cred - deb).round(2)
    raise ValueError("Debe seleccionar Importe único o columnas de Débito y Crédito.")


def _normalizar_descripcion(valor) -> str:
    """Devuelve siempre texto sin sufijos `.0` cuando provienen de números."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, Integral):
        return str(int(valor))
    if isinstance(valor, Real):
        numero = float(valor)
        if math.isfinite(numero) and numero.is_integer():
            return str(int(numero))
        return str(valor)
    return str(valor)


def normalizar_columna_descripcion(serie: pd.Series) -> pd.Series:
    """Normaliza una serie de descripciones garantizando representación textual uniforme."""
    return serie.map(_normalizar_descripcion)


def normalizar_df(
    df_raw: pd.DataFrame,
    fecha_col: str,
    importe_final: pd.Series,
    desc_col: str | None,
    origen: Origen,
    meta: str
) -> list[Movimiento]:
    df = df_raw.copy()
    df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce").dt.floor("d")
    if desc_col and desc_col in df.columns:
        desc_vals = normalizar_columna_descripcion(df[desc_col])
    else:
        desc_vals = pd.Series([""] * len(df), index=df.index)

    out: list[Movimiento] = []
    for f, imp, d in zip(df[fecha_col], importe_final, desc_vals):
        if pd.isna(f) or pd.isna(imp) or float(imp) == 0.0:
            continue
        out.append(Movimiento(
            fecha=f.date(),
            importe=float(imp),
            descripcion=str(d) if d is not None else "",
            origen=origen,
            meta_origen=meta,
        ))
    return out


def detectar_modo(df: pd.DataFrame) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    """Devuelve (modo, fecha, importe, debito, credito, descripcion) con modo en {"Importe único", "Débito/Crédito", None}."""
    f, i, d, c, desc = detectar_columnas(df)
    if d and c:
        return "Débito/Crédito", f, i, d, c, desc
    if i:
        return "Importe único", f, i, None, None, desc
    return None, f, i, d, c, desc
