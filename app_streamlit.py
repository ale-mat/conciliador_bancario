import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from infra.config import load_config
from infra.export import dataframe_a_excel_bytes
from logic.lectura import calcular_importe_final, detectar_columnas
from logic.conciliacion import conciliar, Parametros
from logic.modelos import Movimiento
from infra.loader_bancos import cargar_banco

# =========================
# Helper para CSV
# =========================
def leer_csv_seguro(file):
    """Intenta leer un CSV probando encodings y separadores comunes."""
    for enc in ["latin1", "utf-8", "cp1252"]:
        for sep in [";", ",", "\t", r"\s{2,}"]:
            try:
                file.seek(0)  # reiniciar puntero
                df = pd.read_csv(file, encoding=enc, sep=sep, engine="python")
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
    raise ValueError(f"❌ No se pudo leer {file.name} con encoding/separador común.")


def leer_csv_banco(file):
    """Intenta usar el loader bancario y cae a heurística si falla."""
    try:
        file.seek(0)
    except Exception:
        pass

    try:
        df, banco_detectado = cargar_banco(file)
        df.attrs["banco_detectado"] = banco_detectado
        return df
    except Exception:
        try:
            file.seek(0)
        except Exception:
            pass
        return leer_csv_seguro(file)

# =========================
# Configuración inicial
# =========================
cfg = load_config("config.yaml")
st.set_page_config(page_title=cfg.app.title, layout=cfg.app.page_layout)
st.title(cfg.app.title)

# =========================
# Instrucciones
# =========================
with st.expander("ℹ️ Cómo usar la conciliación bancaria"):
    st.markdown("""
    ### 📂 Paso 1: Cargar archivos
    - Columna **Banco**: extractos bancarios (CSV, XLSX, XLSM).
    - Columna **Interno**: reportes internos/contables.
    - Si el archivo es Excel, deberás elegir la **hoja**.

    ### 🛠️ Paso 2: Revisar columnas detectadas
    El sistema intenta identificar: **Fecha, Importe, Débito, Crédito y Descripción**.
    Podés ajustar manualmente.

    ### 📅 Paso 3: Filtros
    - Podés aplicar rango de fechas.
    - Los parámetros de **tolerancia** (importe y días) y las opciones de conciliación grupal se aplican solo dentro de ese rango.

    ### 🔎 Paso 4: Conciliación
    - **Conciliados exactos**: fecha + importe + números (si existen).
    - **Sugerencias**: dentro de tolerancias o por coincidencia parcial.
    - **Grupales**: si está habilitado, agrupa movimientos del mismo día (o días cercanos).
    - **No conciliados**: solo en Banco o solo en Interno.

    ### 📊 Paso 5: Resultados
    - Tabla final con filtros por estado y texto.
    - Resumen de estados.
    - Descarga de Excel con fechas reales.
    """)

# =========================
# Upload de archivos
# =========================
col_up1, col_up2 = st.columns(2)

with col_up1:
    archivos_banco = st.file_uploader(
        "Archivos Banco (CSV/XLSX/XLSM)",
        type=["csv", "xlsx", "xlsm"],
        accept_multiple_files=True,
        key="archivos_banco"
    )

with col_up2:
    archivos_interno = st.file_uploader(
        "Archivos Interno (CSV/XLSX/XLSM)",
        type=["csv", "xlsx", "xlsm"],
        accept_multiple_files=True,
        key="archivos_interno"
    )

# =========================
# Procesamiento
# =========================
if archivos_banco and archivos_interno:

    # ---- Leer archivos como DataFrames ----
    dfs_banco, dfs_interno = [], []

    # ----- Banco -----
    for f in archivos_banco:
        if f.name.lower().endswith((".xlsx", ".xlsm")):
            xls = pd.ExcelFile(f, engine="openpyxl")
            if len(xls.sheet_names) == 1:
                hoja_b = xls.sheet_names[0]
            else:
                hoja_b = st.selectbox(
                    f"Banco: seleccione hoja de {f.name}",
                    xls.sheet_names,
                    key=f"Banco_{f.name}"
                )
            df_b = pd.read_excel(f, sheet_name=hoja_b)
        else:
            buffer = io.BytesIO(f.getvalue())
            buffer.name = f.name
            df_b = leer_csv_banco(buffer)
        dfs_banco.append(df_b)

    # ----- Interno -----
    for f in archivos_interno:
        if f.name.lower().endswith((".xlsx", ".xlsm")):
            xls = pd.ExcelFile(f, engine="openpyxl")
            if len(xls.sheet_names) == 1:
                hoja_i = xls.sheet_names[0]
            else:
                hoja_i = st.selectbox(
                    f"Interno: seleccione hoja de {f.name}",
                    xls.sheet_names,
                    key=f"Interno_{f.name}"
                )
            df_i = pd.read_excel(f, sheet_name=hoja_i)
        else:
            buffer = io.BytesIO(f.getvalue())
            buffer.name = f.name
            df_i = leer_csv_banco(buffer)
        dfs_interno.append(df_i)

    df_banco = pd.concat(dfs_banco, ignore_index=True)
    df_interno = pd.concat(dfs_interno, ignore_index=True)

    # ---- Detectar columnas automáticamente ----
    f_b, i_b, deb_b, cred_b, d_b = detectar_columnas(df_banco)
    f_i, i_i, deb_i, cred_i, d_i = detectar_columnas(df_interno)

    # ---- Selección de columnas en dos columnas ----
    st.subheader("Mapeo de columnas")
    colB, colI = st.columns(2)

    # ---------- BLOQUE BANCO ----------
    with colB:
        st.markdown("**Banco**")

        modo_sugerido_b = "Débito/Crédito" if (deb_b in df_banco.columns and cred_b in df_banco.columns) else "Importe único"
        idx_radio_b = 1 if modo_sugerido_b == "Débito/Crédito" else 0

        f_b = st.selectbox("Fecha (Banco)", df_banco.columns,
                           index=(df_banco.columns.get_loc(f_b) if f_b in df_banco.columns else 0),
                           key="fecha_b")

        modo_b = st.radio("Banco: ¿Importe único o Débito/Crédito?",
                          ["Importe único", "Débito/Crédito"], index=idx_radio_b, key="modo_b")

        if modo_b == "Importe único":
            i_b = st.selectbox("Importe (Banco)", df_banco.columns,
                               index=(df_banco.columns.get_loc(i_b) if i_b in df_banco.columns else 0),
                               key="imp_b")
            deb_b = cred_b = None
        else:
            deb_b = st.selectbox("Débito (Banco)", df_banco.columns,
                                 index=(df_banco.columns.get_loc(deb_b) if deb_b in df_banco.columns else 0),
                                 key="deb_b")
            cred_b = st.selectbox("Crédito (Banco)", df_banco.columns,
                                  index=(df_banco.columns.get_loc(cred_b) if cred_b in df_banco.columns else 0),
                                  key="cred_b")
            i_b = None

        d_b = st.selectbox("Descripción (Banco)", df_banco.columns,
                           index=(df_banco.columns.get_loc(d_b) if d_b in df_banco.columns else 0),
                           key="desc_b")

    # ---------- BLOQUE INTERNO ----------
    with colI:
        st.markdown("**Interno**")

        modo_sugerido_i = "Débito/Crédito" if (deb_i in df_interno.columns and cred_i in df_interno.columns) else "Importe único"
        idx_radio_i = 1 if modo_sugerido_i == "Débito/Crédito" else 0

        f_i = st.selectbox("Fecha (Interno)", df_interno.columns,
                           index=(df_interno.columns.get_loc(f_i) if f_i in df_interno.columns else 0),
                           key="fecha_i")

        modo_i = st.radio("Interno: ¿Importe único o Débito/Crédito?",
                          ["Importe único", "Débito/Crédito"], index=idx_radio_i, key="modo_i")

        if modo_i == "Importe único":
            i_i = st.selectbox("Importe (Interno)", df_interno.columns,
                               index=(df_interno.columns.get_loc(i_i) if i_i in df_interno.columns else 0),
                               key="imp_i")
            deb_i = cred_i = None
        else:
            deb_i = st.selectbox("Débito (Interno)", df_interno.columns,
                                 index=(df_interno.columns.get_loc(deb_i) if deb_i in df_interno.columns else 0),
                                 key="deb_i")
            cred_i = st.selectbox("Crédito (Interno)", df_interno.columns,
                                  index=(df_interno.columns.get_loc(cred_i) if cred_i in df_interno.columns else 0),
                                  key="cred_i")
            i_i = None

        d_i = st.selectbox("Descripción (Interno)", df_interno.columns,
                           index=(df_interno.columns.get_loc(d_i) if d_i in df_interno.columns else 0),
                           key="desc_i")

    # ---- Calcular importe final ----
    df_banco["importe_final"] = calcular_importe_final(df_banco, i_b, deb_b, cred_b)
    df_interno["importe_final"] = calcular_importe_final(df_interno, i_i, deb_i, cred_i)

    # ---- Convertir a objetos Movimiento ----
    movs_banco = [
        Movimiento(f.date(), float(imp), str(desc), "Banco")
        for f, imp, desc in zip(pd.to_datetime(df_banco[f_b], errors="coerce"), df_banco["importe_final"], df_banco[d_b])
        if pd.notna(f) and pd.notna(imp) and imp != 0
    ]
    movs_interno = [
        Movimiento(f.date(), float(imp), str(desc), "Interno")
        for f, imp, desc in zip(pd.to_datetime(df_interno[f_i], errors="coerce"), df_interno["importe_final"], df_interno[d_i])
        if pd.notna(f) and pd.notna(imp) and imp != 0
    ]

    # ---- Parámetros de conciliación ----
    st.subheader("Parámetros de conciliación")
    colp1, colp2, colp3, colp4 = st.columns(4)

    with colp1:
        tol_importe = st.number_input("Tolerancia importe (±)",
                                      value=float(cfg.conciliacion.tolerancia_importe_default),
                                      step=0.01, format="%.2f")
    with colp2:
        tol_dias = st.number_input("Tolerancia días",
                                   value=int(cfg.conciliacion.tolerancia_dias_default),
                                   min_value=0, step=1)
    with colp3:
        permitir_grupal = st.checkbox("Permitir conciliación grupal",
                                      value=cfg.conciliacion.permitir_conciliacion_grupal)
    with colp4:
        permitir_grupos_fuera = st.checkbox("Permitir grupos fuera de fecha",
                                            value=cfg.conciliacion.permitir_grupos_fuera_de_fecha)

    parametros = Parametros(
        tolerancia_dias=tol_dias,
        tolerancia_importe=tol_importe,
        permitir_conciliacion_grupal=permitir_grupal,
        permitir_grupos_fuera_de_fecha=permitir_grupos_fuera,
    )

    # ---- Conciliación ----
    matches, pend_b, pend_i = conciliar(movs_banco, movs_interno, parametros)

    # ---- Construcción de tabla de salida ----
    rows = []
    for m in matches:
        rows.append({
            "fecha_banco": getattr(m, "fecha_banco", None),
            "importe_banco": getattr(m, "importe_banco", None),
            "desc_banco": getattr(m, "desc_banco", ""),
            "fecha_interno": getattr(m, "fecha_interno", None),
            "importe_interno": getattr(m, "importe_interno", None),
            "desc_interno": getattr(m, "desc_interno", ""),
            "estado": getattr(m, "estado", "Sin estado"),
            "correccion_sugerida": getattr(m, "correccion_sugerida", ""),
        })

    for m in pend_b:
        rows.append({
            "fecha_banco": m.fecha,
            "importe_banco": m.importe,
            "desc_banco": m.descripcion,
            "fecha_interno": pd.NaT,
            "importe_interno": pd.NA,
            "desc_interno": "",
            "estado": "No conciliado (solo Banco)",
            "correccion_sugerida": "Cargar en Interno / revisar",
        })
    for m in pend_i:
        rows.append({
            "fecha_banco": pd.NaT,
            "importe_banco": pd.NA,
            "desc_banco": "",
            "fecha_interno": m.fecha,
            "importe_interno": m.importe,
            "desc_interno": m.descripcion,
            "estado": "No conciliado (solo Interno)",
            "correccion_sugerida": "Cargar en Banco / revisar",
        })

    salida = pd.DataFrame(rows)

    # ---- Vista con filtros ----
    st.markdown("**Resultado**")
    salida_filtrada = salida
    if "estado" in salida.columns:
        estados_unicos = sorted(salida["estado"].dropna().unique().tolist())
        estados_sel = st.multiselect(
            "Filtrar por estado",
            estados_unicos,
            default=estados_unicos,
        )
        salida_filtrada = salida[salida["estado"].isin(estados_sel)]

    filtro_texto = st.text_input("Buscar en descripciones", "")
    if filtro_texto:
        salida_filtrada = salida_filtrada[
            salida_filtrada["desc_banco"].str.contains(filtro_texto, case=False, na=False)
            | salida_filtrada["desc_interno"].str.contains(filtro_texto, case=False, na=False)
        ]

    # ---- Mostrar tabla ----
    def formatear_df_ui(df: pd.DataFrame):
        formatos = {}
        if "fecha_banco" in df.columns:
            formatos["fecha_banco"] = lambda x: x.strftime("%d/%m/%Y") if pd.notnull(x) else ""
        if "fecha_interno" in df.columns:
            formatos["fecha_interno"] = lambda x: x.strftime("%d/%m/%Y") if pd.notnull(x) else ""
        for col in ["importe_banco", "importe_interno"]:
            if col in df.columns:
                formatos[col] = lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notnull(x) else ""
        return df.style.format(formatos)

    st.dataframe(formatear_df_ui(salida_filtrada), use_container_width=True)

    # ---- Resumen ----
    st.markdown("**Resumen**")

    # Clasificación dinámica en pilares
    def clasificar_estado(estado: str) -> str:
        if estado.startswith("Conciliado"):
            return "Conciliados"
        elif estado.startswith("Sugerido"):
            return "Sugeridos"
        elif estado.startswith("No conciliado"):
            return "No conciliados"
        return "Otros"

    if "estado" in salida_filtrada.columns:
        # Contar por estado
        resumen_counts = salida_filtrada["estado"].value_counts()

        # Agregar columna pilar y ordenar por ella
        resumen = (
            resumen_counts
            .rename_axis("Estado")
            .reset_index(name="Cantidad")
            .assign(Pilar=lambda df: df["Estado"].apply(clasificar_estado))
            .sort_values(
                ["Pilar", "Estado"],
                key=lambda col: col.map({"Conciliados": 1, "Sugeridos": 2, "No conciliados": 3, "Otros": 4}),
            )
            .reset_index(drop=True)
        )

        st.dataframe(resumen, use_container_width=True)

    # ---- Exportar a Excel ----
    formato_columnas_fecha = {"fecha_banco": "DD/MM/YYYY", "fecha_interno": "DD/MM/YYYY"}
    xls_bytes = dataframe_a_excel_bytes(
        salida, sheet_name="Conciliacion", formato_columnas_fecha=formato_columnas_fecha
    )
    st.download_button("Descargar conciliación (xlsx)", data=xls_bytes, file_name="conciliacion.xlsx")
