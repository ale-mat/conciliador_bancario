import pandas as pd

from logic.lectura import detectar_modo, normalizar_columna_descripcion


def test_detectar_modo_dc():
    df = pd.DataFrame({
        "Fecha": ["2025-01-01"],
        "Débito": [100],
        "Crédito": [0],
        "Detalle": ["Prueba"],
    })
    modo, f, i, d, c, desc = detectar_modo(df)
    assert modo == "Débito/Crédito"
    assert d == "Débito"
    assert c == "Crédito"


def test_detectar_modo_dc_signo_pregunta():
    df = pd.DataFrame({
        "Fecha": ["2025-01-01"],
        "D?bito": [100],
        "Cr?dito": [0],
        "Detalle": ["Prueba"],
    })
    modo, f, i, d, c, desc = detectar_modo(df)
    assert modo == "Débito/Crédito"
    assert d == "D?bito"
    assert c == "Cr?dito"


def test_normalizar_columna_descripcion_numeros():
    serie = pd.Series([48923.0, 48924, "48925", None, float("nan"), 51234.50])
    normalizada = normalizar_columna_descripcion(serie)
    assert normalizada.tolist() == ["48923", "48924", "48925", "", "", "51234.5"]
