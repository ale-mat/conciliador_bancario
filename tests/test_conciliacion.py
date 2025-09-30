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
