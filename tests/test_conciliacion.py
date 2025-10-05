from datetime import date
from logic.modelos import Movimiento
from logic.conciliacion import conciliar, Parametros


def test_exactos_por_numero():
    b = [Movimiento(date(2025, 1, 10), 5000.00, "Transferencia 1461 Ref 5678", "Banco")]
    i = [Movimiento(date(2025, 1, 10), 5000.00, "Pago 1461", "Interno")]
    m, pb, pi = conciliar(b, i, Parametros())
    assert any(x.estado == "Conciliado exacto" for x in m)
    assert not pb and not pi


def test_no_exacto_si_solo_un_lado_tiene_numeros():
    b = [Movimiento(date(2025, 1, 10), 5000.00, "Transferencia 1461", "Banco")]
    i = [Movimiento(date(2025, 1, 10), 5000.00, "Transferencia cliente", "Interno")]
    m, pb, pi = conciliar(b, i, Parametros())
    assert any(x.estado != "Conciliado exacto" for x in m)


def test_duplicados_mismo_importe_misma_fecha():
    """Dos movimientos con mismo importe y fecha -> deben emparejarse 1 a 1, sin duplicación."""
    banco = [
        Movimiento(date(2023,12,20), 1000, "TRANSFER 1111 CLIENTE A", "Banco"),
        Movimiento(date(2023,12,20), 1000, "TRANSFER 2222 CLIENTE B", "Banco")
    ]
    interno = [
        Movimiento(date(2023,12,20), 1000, "TRANSFER 1111 CLIENTE A", "Interno"),
        Movimiento(date(2023,12,20), 1000, "TRANSFER 3333 CLIENTE C", "Interno")
    ]

    matches, pend_b, pend_i = conciliar(banco, interno, Parametros())
    assert len(matches) == 2
    assert not pend_b and not pend_i
    usados_internos = [(m.fecha_interno, m.importe_interno, m.desc_interno) for m in matches]
    assert len(usados_internos) == len(set(usados_internos)), "Un interno se usó más de una vez"


def test_varios_iguales_texto_diferente():
    """5 movimientos con mismo importe y fecha pero descripciones diferentes."""
    banco = [Movimiento(date(2023,12,21), 500, f"DESC {i}", "Banco") for i in range(5)]
    interno = [Movimiento(date(2023,12,21), 500, f"DESC {i}", "Interno") for i in range(5)]

    matches, pend_b, pend_i = conciliar(banco, interno, Parametros())
    assert len(matches) == 5
    assert not pend_b and not pend_i


def test_coincidencia_textual_vs_no_textual():
    """Mismo importe y fecha pero descripciones sin overlap -> debería sugerir, no exacto."""
    banco = [Movimiento(date(2023,12,22), 200, "PAGO CLIENTE JUAN", "Banco")]
    interno = [Movimiento(date(2023,12,22), 200, "TRANSFERENCIA CLIENTE MARIA", "Interno")]

    matches, _, _ = conciliar(banco, interno, Parametros())
    assert matches[0].estado.startswith("Sugerido"), "Debería sugerir, no marcar como exacto"


def test_coincidencia_por_numero():
    """Coincidencia solo por número dentro de descripción."""
    banco = [Movimiento(date(2023,12,23), 300, "PAGO REF 12345", "Banco")]
    interno = [Movimiento(date(2023,12,23), 300, "RECIBO #12345", "Interno")]

    matches, _, _ = conciliar(banco, interno, Parametros())
    assert any("Conciliado exacto" in m.estado or "Sugerido (descripción)" in m.estado for m in matches)


def test_tolerancia_importe_y_dias():
    """Diferencias pequeñas en fecha/importe dentro de tolerancia -> debe sugerir."""
    banco = [Movimiento(date(2023,12,24), 1000, "TEST A", "Banco")]
    interno = [Movimiento(date(2023,12,25), 1001, "TEST A", "Interno")]  # +1 día, +1 importe

    params = Parametros(tolerancia_importe=2.0, tolerancia_dias=2)
    matches, _, _ = conciliar(banco, interno, params)
    assert matches[0].estado.startswith("Sugerido")


def test_grupal_detecta_sumas():
    """3 movimientos de 1000 en banco = 3000, 1 movimiento de 3000 en interno -> grupal."""
    banco = [
        Movimiento(date(2023,12,26), 1000, "A", "Banco"),
        Movimiento(date(2023,12,26), 1000, "B", "Banco"),
        Movimiento(date(2023,12,26), 1000, "C", "Banco")
    ]
    interno = [Movimiento(date(2023,12,26), 3000, "SUMA", "Interno")]

    params = Parametros(permitir_conciliacion_grupal=True)
    matches, _, _ = conciliar(banco, interno, params)
    assert any("grupal" in m.estado.lower() for m in matches)


def test_casos_sin_match():
    """Ningún match posible -> todo queda pendiente."""
    banco = [Movimiento(date(2023,12,27), 999, "X", "Banco")]
    interno = [Movimiento(date(2023,12,28), 888, "Y", "Interno")]

    matches, pend_b, pend_i = conciliar(banco, interno, Parametros())
    assert not matches
    assert len(pend_b) == 1 and len(pend_i) == 1
