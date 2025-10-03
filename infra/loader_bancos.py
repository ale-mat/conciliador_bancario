import io
import math
import numbers
from typing import Tuple, Union, TextIO, BinaryIO

import pandas as pd
import re
import unicodedata

from infra.config import load_config


# ==============================
# Configuracion de bancos
# ==============================
BANCOS = {
    "galicia": {
        "sep": ";",
        "decimal": ",",
        "encoding": "utf-8-sig",
        "fecha_format": "%d/%m/%Y",
        "cols": [
            "Fecha",
            "Descripción",
            "Origen",
            "Débitos",
            "Créditos",
            "Grupo de Conceptos",
            "Concepto",
            "Número de Terminal",
            "Observaciones Cliente",
            "Número de Comprobante",
            "Leyendas Adicionales1",
            "Leyendas Adicionales2",
            "Leyendas Adicionales3",
            "Leyendas Adicionales4",
            "Tipo de Movimiento",
            "Saldo",
        ],
        "nombre": "Banco Galicia",
    },
    "nacion": {
        "sep": ",",
        "decimal": ",",
        "encoding": "latin1",
        "fecha_format": "%d/%m/%Y",
        "cols": ["Fecha", "Comprobante", "Concepto", "Importe", "Saldo"],
        "nombre": "Banco NaciÃ³n",
    },
    "supervielle": {
        "sep": ",",
        "decimal": ",",
        "encoding": "latin1",  # suele ser cp1252 también
        "fecha_format": "%Y/%m/%d %H:%M",
        "cols": ["Fecha", "Concepto", "Detalle", "Descripcion", "Debito", "Credito", "Saldo"],
        "nombre": "Banco Supervielle",
    },
    "ciudad": {
        "sep": ";",
        "decimal": ",",
        "encoding": "latin1",   # o cp1252, ambos sirven
        "fecha_format": "%d/%m/%Y",
        "cols": [
            "Cuenta",
            "CUIT Cuenta",
            "Fecha",
            "Monto",
            "N° de Comprobante",   # con símbolo correcto
            "Descripción",
            "Saldo",
        ],
        "nombre": "Banco Ciudad",
    },
}


_CONFIG = load_config("config.yaml")


def _as_text_io(obj: Union[str, TextIO, BinaryIO]) -> Tuple[TextIO, bool]:
    """Return a text IO (latin1) and whether it's a temporary wrapper.

    Accepts path, text IO, or binary IO. Ensures seekable and positioned at start.
    """
    if isinstance(obj, str):
        f = open(obj, "r", encoding="latin1", errors="replace")
        return f, True

    # Streamlit UploadedFile is binary and seekable
    if hasattr(obj, "read"):
        # Reset pointer if seekable
        try:
            obj.seek(0)
        except Exception:
            pass

        if isinstance(obj, io.TextIOBase):
            return obj, False
        else:
            # Binary -> wrap to text with latin1 for robust header read
            wrapper = io.TextIOWrapper(obj, encoding="latin1", errors="replace")
            try:
                wrapper.seek(0)
            except Exception:
                pass
            return wrapper, True

    raise TypeError("Objeto de archivo no soportado para lectura de cabecera")


def _demojibake_text(s: str) -> str:
    """Attempt to fix typical UTF-8 text decoded as latin1/cp1252 (mojibake).

    Tries re-encoding to bytes with latin1/cp1252 and decoding back to utf-8.
    Chooses the candidate with fewer mojibake artifacts (Ã, Ã, ï¿½).
    """
    if not isinstance(s, str):
        return s
    candidates = [s]
    for src in ("latin1", "cp1252"):
        try:
            fixed = s.encode(src, errors="ignore").decode("utf-8", errors="ignore")
            candidates.append(fixed)
        except Exception:
            pass

    def score(text: str) -> int:
        return sum(text.count(b) for b in ("Ã", "Ã", "ï¿½"))

    best = min(candidates, key=score)
    # Remove BOM if reconstituted
    return best.lstrip("\ufeff")


def _split_header(line: str) -> list:
    """Split header trying common separators and stripping quotes/spaces.

    Handles BOM and empty lines gracefully.
    """
    line = _demojibake_text(str(line))
    line = line.replace("ï»¿", "").lstrip("\ufeff").strip()  # Quitar BOM real y mojibake ("ï»¿")
    if not line:
        return []
    cand_seps = {",", ";", "\t"}
    # Try to detect by presence count; pick the most likely
    best = max(cand_seps, key=lambda s: line.count(s))
    parts = [p.strip().strip('"').strip("'") for p in line.split(best)]
    # remove empties in case of trailing separator
    return [p for p in parts if p]


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    return normalized.encode("ascii", "ignore").decode("ascii", "ignore")


def _keyize(text: str) -> str:
    """Key form for tolerant comparisons: lowercased, accentless, alnum+space only.

    Also patches common broken-encoding patterns like D?bito/Cr?dito/Descripci?n/N?mero.
    """
    text = str(text)
    text = text.replace("\ufeff", "").replace("ï»¿", "") # Eliminar BOM en ambas formas
    for bad, good in (
        ("Ã¡", "á"),
        ("Ã©", "é"),
        ("Ã­", "í"),
        ("Ã³", "ó"),
        ("Ãº", "ú"),
        ("Ã±", "ñ"),
        ("Ã", "a"),
        ("Â", ""),
    ):
        text = text.replace(bad, good)
    t = _strip_accents(_demojibake_text(text)).lower()
    t = re.sub(r"d.?bito", "debito", t)
    t = re.sub(r"cr.?dito", "credito", t)
    t = re.sub(r"descripci.?n", "descripcion", t)
    t = re.sub(r"n.?mero", "numero", t)
    t = t.replace("ï¿½", "")
    t = re.sub(r"[^0-9a-z\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_DESCRIP_RAW = (_CONFIG.conciliacion.campos_descripcion or [])
_DESCRIP_KEYS = {_keyize(name) for name in _DESCRIP_RAW}
_DESCRIP_KEYS.add("descripcion")


def _build_expected_keymap(cols: list[str]) -> dict[str, str]:
    """Map from normalized keys to canonical expected column names."""
    mapping: dict[str, str] = {}
    for c in cols:
        mapping[_keyize(c)] = c
    return mapping


def _canonicalize_columns(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Devuelve un DataFrame con columnas canÃ³nicas ordenadas y extras al final.

    - Usa _keyize para mapear columnas existentes a la lista cfg['cols']
    - Mantiene solo la primera coincidencia para evitar duplicados
    - Inserta columnas faltantes con NA
    - Concatena columnas extra (no mapeadas) al final, sin duplicados
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    exp_cols = cfg["cols"]
    key_to_expected = { _keyize(c): c for c in exp_cols }

    # Primer match existente por clave normalizada
    key_to_source: dict[str, str] = {}
    for col in df.columns:
        key = _keyize(col)
        if key in key_to_expected and key not in key_to_source:
            key_to_source[key] = col

    aligned: dict[str, pd.Series] = {}
    for exp in exp_cols:
        key = _keyize(exp)
        if key in key_to_source:
            aligned[exp] = df[key_to_source[key]].copy()
        else:
            aligned[exp] = pd.Series(pd.NA, index=df.index, name=exp)

    result = pd.DataFrame(aligned)

    # Extras (columnas no mapeadas), preservando orden original y evitando duplicados
    mapped_cols = set(key_to_source.values())
    extras: list[str] = []
    for col in df.columns:
        if col in mapped_cols:
            continue
        if col in extras or col in result.columns:
            continue
        extras.append(col)

    if extras:
        extras_df = df[extras].copy()
        # Quitar duplicados por nombre en extras
        extras_df = extras_df.loc[:, ~extras_df.columns.duplicated(keep="first")]
        result = pd.concat([result, extras_df], axis=1)

    # Asegurar unicidad final
    if result.columns.duplicated().any():
        result = result.loc[:, ~result.columns.duplicated(keep="first")]

    return result


def _normalize_desc_value(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str):
        text = _demojibake_text(value).strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered in {"nan", "none", "null"}:
            return None
        return text
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        if math.isnan(float(value)):
            return None
        if float(value).is_integer():
            return str(int(value))
        text = f"{value}"
        text = text.rstrip("0").rstrip(".")
        return text
    text = str(value).strip()
    if not text:
        return None
    return text


def _unificar_descripcion(df: pd.DataFrame, banco_cfg: dict) -> pd.DataFrame:
    """Combina columnas descriptivas en una Ãºnica columna canÃ³nica."""
    if not _DESCRIP_KEYS:
        return df

    desc_candidates = [col for col in df.columns if _keyize(col) in _DESCRIP_KEYS]
    if not desc_candidates:
        return df

    expected_cols = banco_cfg.get("cols", [])
    desc_target = None
    for col in expected_cols:
        if _keyize(col) == "descripcion":
            desc_target = col
            break
    if desc_target is None:
        return df

    subset = df[desc_candidates]
    combined_values: list[object] = []
    for row in subset.itertuples(index=False, name=None):
        seen: set[str] = set()
        parts: list[str] = []
        for val in row:
            text = _normalize_desc_value(val)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            parts.append(text)
        combined_values.append(" ".join(parts) if parts else pd.NA)

    combined_series = pd.Series(combined_values, index=df.index, dtype="object", name=desc_target)

    descripcion_cols = [col for col in df.columns if _keyize(col) == "descripcion"]
    df_result = df.drop(columns=descripcion_cols, errors="ignore")

    df_result[desc_target] = combined_series

    ordered_cols: list[str] = []
    for col in expected_cols:
        if col in df_result.columns and col not in ordered_cols:
            ordered_cols.append(col)
    extras = [col for col in df_result.columns if col not in ordered_cols]
    df_result = df_result[ordered_cols + extras]

    return df_result


def detectar_banco_tolerante(path_or_file: Union[str, TextIO, BinaryIO]) -> str:
    """Detecta el banco comparando cabeceras de forma tolerante a encoding/acentos."""
    f, is_temp = _as_text_io(path_or_file)
    try:
        # Leer hasta encontrar una lÃ­nea no vacÃ­a de cabecera
        first = ""
        while True:
            chunk = f.readline()
            if not chunk:
                break  # EOF
            if _split_header(chunk):
                first = chunk
                break
    finally:
        try:
            f.seek(0)
        except Exception:
            pass
        if is_temp:
            try:
                f.detach()
            except Exception:
                try:
                    f.close()
                except Exception:
                    pass

    cols = _split_header(first)
    cols_keys = [_keyize(c) for c in cols]

    for banco, cfg in BANCOS.items():
        esperado = cfg["cols"]
        esperado_keys = [_keyize(c) for c in esperado]
        if cols_keys[: len(esperado_keys)] == esperado_keys or (
            len(cols_keys) >= 2 and esperado_keys[:2] == cols_keys[:2]
        ):
            return banco
    raise ValueError(f"â ï¸ No se pudo detectar el banco automÃ¡ticamente. Cabecera leÃ­da: {cols}")


def validar_columnas_tolerante(df: pd.DataFrame, banco: str) -> None:
    esperado = BANCOS[banco]["cols"]
    cols = [str(c).strip() for c in df.columns.tolist()]
    exp_keys = [_keyize(c) for c in esperado]
    got_keys = [_keyize(c) for c in cols]
    if got_keys[: len(exp_keys)] != exp_keys:
        nombre = BANCOS[banco].get("nombre", banco.title())
        raise ValueError(
            f"â ï¸ Formato inesperado en {nombre}. Se esperaban {esperado}, se obtuvo {cols}"
        )


def detectar_banco(path_or_file: Union[str, TextIO, BinaryIO]) -> str:
    """Detecta el banco segÃºn columnas conocidas en cabecera.

    Acepta rutas o archivos en memoria (incluido Streamlit UploadedFile).
    """
    f, is_temp = _as_text_io(path_or_file)
    try:
        first = f.readline()
    finally:
        try:
            f.seek(0)
        except Exception:
            pass
        if is_temp:
            try:
                f.detach()  # in case of TextIOWrapper over binary
            except Exception:
                try:
                    f.close()
                except Exception:
                    pass

    cols = _split_header(first)

    # Try exact/prefix match against known configs
    for banco, cfg in BANCOS.items():
        esperado = cfg["cols"]
        if cols[: len(esperado)] == esperado or (
            len(cols) >= 2 and esperado[:2] == cols[:2]
        ):
            return banco

    raise ValueError("â ï¸ No se pudo detectar el banco automÃ¡ticamente por cabecera")


def validar_columnas(df: pd.DataFrame, banco: str) -> None:
    """Valida que las columnas coincidan con lo esperado para el banco."""
    esperado = BANCOS[banco]["cols"]
    cols = [str(c).strip() for c in df.columns.tolist()]
    if cols[: len(esperado)] != esperado:
        nombre = BANCOS[banco].get("nombre", banco.title())
        raise ValueError(
            f"â ï¸ Formato inesperado en {nombre}. Se esperaban {esperado}, se obtuvo {cols}"
        )


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def normalizar_importes(df: pd.DataFrame, banco: str) -> pd.DataFrame:
    """Convierte importes a float segÃºn reglas de cada banco."""
    if banco == "nacion":
        for col in ["Importe", "Saldo"]:
            if col in df.columns:
                s = df[col].astype(str).str.replace(r"[\$\.]", "", regex=True)
                s = s.str.replace(",", ".", regex=False)
                df[col] = _to_float(s)
    elif banco == "supervielle":
        for col in ["Debito", "Credito", "Saldo"]:
            if col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    continue
                s = df[col].astype(str).str.replace(".", "", regex=False)
                s = s.str.replace(",", ".", regex=False)
                df[col] = _to_float(s)
    elif banco in ["galicia", "ciudad"]:
        # pandas respeta decimal="," en read_csv; no acciÃ³n adicional
        pass
    return df


def cargar_banco(path_or_file: Union[str, TextIO, BinaryIO]) -> Tuple[pd.DataFrame, str]:
    """Carga un extracto bancario, normaliza y devuelve (df, banco).

    Acepta ruta o archivo en memoria (UploadedFile). No persiste archivos.
    """
    banco = detectar_banco_tolerante(path_or_file)
    cfg = BANCOS[banco]

    # Para pandas, necesitamos un manejador reposicionado al inicio
    file_obj: Union[str, BinaryIO, TextIO]
    if isinstance(path_or_file, str):
        file_obj = path_or_file
    else:
        try:
            path_or_file.seek(0)
        except Exception:
            pass
        file_obj = path_or_file

    df = None
    last_err: Exception | None = None

    # Caso especial: Banco Galicia (UTF-8 con BOM, comillas y ; final)
    if banco == "galicia":
        try:
            df = pd.read_csv(
                file_obj,
                sep=cfg["sep"],
                decimal=cfg["decimal"],
                encoding="utf-8-sig",  # limpia BOM
                engine="python",
                quotechar='"',         # importante para DescripciÃ³n
                skip_blank_lines=True,
                header=0,
                index_col=False,
            )
            # Eliminar solo columnas realmente extra por ';' final
            expected_keys = { _keyize(c) for c in cfg["cols"] }
            to_drop = []
            for col in df.columns:
                name = str(col)
                k = _keyize(name)
                if (name.strip() == "" or name.startswith("Unnamed")) and df[col].isna().all():
                    to_drop.append(col)
                elif k == "" and df[col].isna().all():
                    to_drop.append(col)
                # no eliminar columnas esperadas aunque estÃ©n vacÃ­as
            if to_drop:
                df.drop(columns=to_drop, inplace=True)

            # Renombrar a canÃ³nico y reordenar antes de validar
            exp_cols = cfg["cols"]
            key_to_canonical = { _keyize(c): c for c in exp_cols }
            rename_map: dict[str, str] = {}
            for c in list(df.columns):
                k = _keyize(c)
                if k in key_to_canonical:
                    rename_map[c] = key_to_canonical[k]
            if rename_map:
                df = df.rename(columns=rename_map)
            if all(col in df.columns for col in exp_cols):
                df = df[exp_cols]

            # ValidaciÃ³n tolerante (ya renombrado)
            validar_columnas_tolerante(df, banco)
        except Exception as e:
            raise ValueError(f"Error leyendo CSV de Galicia: {e}")

    else:
        # Intentar con mÃºltiples encodings comunes
        preferred = ("utf-8-sig", "utf-8", "cp1252")
        first_enc = cfg.get("encoding", "latin1")
        encodings_try: list[str] = []
        for enc in (*preferred, first_enc, "latin1"):
            if enc not in encodings_try:
                encodings_try.append(enc)

        selected_enc: str | None = None
        for enc in encodings_try:
            try:
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
            except Exception:
                pass
            try:
                common_kwargs = dict(
                    sep=cfg["sep"],
                    decimal=cfg["decimal"],
                    encoding=enc,
                    engine="python",
                    skip_blank_lines=True,
                )
                if banco == "supervielle":
                    # Leer todo como texto para evitar inferencias erróneas
                    candidate = pd.read_csv(
                        file_obj,
                        sep=cfg["sep"],
                        decimal=cfg["decimal"],
                        encoding=enc,
                        engine="python",
                        skip_blank_lines=True,
                        dtype=str,
                        keep_default_na=False,
                    )
                    # Renombrar columnas comunes a canónicas
                    rename_map = {
                        "D?bito": "Debito", "Débito": "Debito",
                        "Cr?dito": "Credito", "Credito": "Credito",
                        "Detalle": "Detalle", "Concepto": "Concepto",
                        "Saldo": "Saldo", "Descripcion": "Descripcion",
                    }
                    candidate = candidate.rename(columns={c: rename_map.get(c, c) for c in candidate.columns})
                else:
                    candidate = pd.read_csv(file_obj, **common_kwargs)

                # Fallback: si quedÃ³ una sola columna, intentar auto-detectar separador
                if banco == "supervielle" and "Descripción" not in candidate.columns:
                    idx = candidate.columns.get_loc("Detalle") + 1 if "Detalle" in candidate.columns else len(candidate.columns)
                    candidate.insert(idx, "Descripción", pd.NA)
                if candidate.shape[1] == 1:
                    try:
                        if hasattr(file_obj, "seek"):
                            file_obj.seek(0)
                    except Exception:
                        pass
                    try:
                        autodetect = pd.read_csv(
                            file_obj,
                            sep=None,
                            engine="python",
                            encoding=enc,
                            decimal=cfg["decimal"],
                            skip_blank_lines=True,
                            keep_default_na=False,
                        )
                        candidate = autodetect
                    except Exception:
                        pass
                validar_columnas_tolerante(candidate, banco)
                df = candidate
                selected_enc = enc
                break
            except Exception as e:
                last_err = e
                continue

        if df is None:
            raise last_err if last_err else ValueError(
                f"No se pudo leer el CSV de {banco} con encodings comunes"
            )

    # Normalizar importes (incluye caso Supervielle forzando texto -> float)
    if banco == "supervielle":
        raw_df = None
        try:
            # Releer como texto crudo para obtener los importes con coma
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            raw_df = pd.read_csv(
                file_obj,
                sep=cfg["sep"],
                encoding=selected_enc or cfg.get("encoding", "latin1"),
                engine="python",
                skip_blank_lines=True,
                dtype=str,
                keep_default_na=False,
            )
        except Exception:
            raw_df = None

        for c in ["Debito", "Credito", "Saldo"]:
            if c in df.columns:
                source_series = raw_df[c] if (raw_df is not None and c in raw_df.columns) else df[c]
                s = source_series.astype(str).str.replace(".", "", regex=False)
                s = s.str.replace(",", ".", regex=False)
                df[c] = _to_float(s)

    # Normalizar fecha
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(
            df["Fecha"].astype(str).str.strip(),
            format=cfg["fecha_format"],
            errors="coerce",
        )

    # Normalizar importes con reglas por banco
    df = normalizar_importes(df, banco)

    # Canonicalizar columnas antes de devolver
    cfg = BANCOS[banco]
    df = _canonicalize_columns(df, cfg)
    df = _unificar_descripcion(df, cfg)
    if "Fecha" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Fecha"]):
        fmt = cfg.get("fecha_format")
        try:
            df["Fecha"] = pd.to_datetime(
                df["Fecha"].astype(str).str.strip(),
                format=fmt if fmt else None,
                errors="coerce",
            )
        except Exception:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df, banco


if __name__ == "__main__":
    # Ejemplo de uso manual (ajustar ruta relativa si corresponde)
    ejemplo = "data/galicia.csv"
    try:
        df_, banco_ = cargar_banco(ejemplo)
        print("Banco detectado:", banco_)
        print(df_.dtypes)
        print(df_.head())
    except FileNotFoundError:
        print("Archivo de ejemplo no encontrado:", ejemplo)
