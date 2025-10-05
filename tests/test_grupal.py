from datetime import date
from logic.modelos import Movimiento
from logic.conciliacion import conciliar, Parametros

def test_grupal_funciona():
    banco = [
        Movimiento(date(2025, 2, 3), 5362393.00, "PAG", "Banco"),
        Movimiento(date(2025, 2, 3), 32324944.00, "PAG", "Banco"),
        Movimiento(date(2025, 2, 3), 15642485.00, "PAG", "Banco"),
    ]
    interno = [
        Movimiento(date(2025, 2, 3), 53329822.00, "Aporte 1", "Interno")
    ]

    m, pb, pi = conciliar(banco, interno, Parametros(
        permitir_conciliacion_grupal=True,
        permitir_grupos_fuera_de_fecha=True,
        tolerancia_importe=1,
        tolerancia_dias=30,
    ))
    assert any(x.estado == "Sugerido (grupal)" for x in m)
