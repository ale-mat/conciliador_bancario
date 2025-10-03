import io
import pytest

from infra.loader_bancos import cargar_banco, BANCOS, _keyize


def test_galicia_loader():
    data = '''"Fecha";"Descripción";"Origen";"Débitos";"Créditos";"Grupo de Conceptos";"Concepto";"Número de Terminal";"Observaciones Cliente";"Número de Comprobante";"Leyendas Adicionales1";"Leyendas Adicionales2";"Leyendas Adicionales3";"Leyendas Adicionales4";"Tipo de Movimiento";"Saldo"
"02/09/2025";"Lorem Ipsum";"";"1000,00";"0";"";"Concepto X";"";"Nota lorem";"ABC123";"Leyenda lorem";"";"";"";"Imputado";"5000,00"
'''
    df, banco = cargar_banco(io.StringIO(data))
    assert banco == "galicia"
    assert df["Fecha"].iloc[0].day == 2
    deb_col = next(col for col in df.columns if _keyize(col) == "debitos")
    assert df[deb_col].iloc[0] == 1000.00
    desc_cols = [col for col in df.columns if _keyize(col) == "descripcion"]
    assert len(desc_cols) == 1
    desc_value = str(df[desc_cols[0]].iloc[0])
    assert "Lorem" in desc_value
    assert "ABC123" in desc_value


def test_nacion_loader():
    data = '''Fecha,Comprobante,Concepto,Importe,Saldo
01/10/2025,12345,PAGO VEP IPSUM,"$ -1.000,50","$ 2.000,75"
'''
    df, banco = cargar_banco(io.StringIO(data))
    assert banco == "nacion"
    assert df["Fecha"].iloc[0].month == 10
    assert df["Importe"].iloc[0] == -1000.50
    assert "Descripción" not in df.columns  # Nación no trae descripción


def test_supervielle_loader():
    data = '''Fecha,Concepto,Detalle,Débito,Crédito,Saldo
2025/10/02 10:26,Lorem Transferencia,Detalle lorem,"0,00","500,00","1.000,00"
'''
    df, banco = cargar_banco(io.StringIO(data))
    assert banco == "supervielle"
    assert df["Fecha"].iloc[0].year == 2025
    cred_col = next(col for col in df.columns if _keyize(col) == "credito")
    assert df[cred_col].iloc[0] == 500.00
    # verificar que exista columna "descripcion"
    desc_cols = [col for col in df.columns if _keyize(col) == "descripcion"]
    assert len(desc_cols) == 1
    desc_value = str(df[desc_cols[0]].iloc[0])
    assert "Lorem" in desc_value
    assert "Detalle" in desc_value


def test_ciudad_loader():
    data = '''Cuenta;CUIT Cuenta;Fecha;Monto;N° de Comprobante;Descripción;Saldo;Observaciones
CC $ 1234567890;20123456789;01/10/2025;-1234,56;67890;SUELDO IPSUM;5000,00;Obs lorem
'''
    df, banco = cargar_banco(io.StringIO(data))
    assert banco == "ciudad"
    assert df["Fecha"].iloc[0].month == 10
    assert str(df["Fecha"].dtype).startswith("datetime64")
    assert df["Monto"].iloc[0] == -1234.56
    desc_cols = [col for col in df.columns if _keyize(col) == "descripcion"]
    assert len(desc_cols) == 1
    desc_ciudad = str(df[desc_cols[0]].iloc[0])
    assert "67890" in desc_ciudad
    assert "SUELDO" in desc_ciudad
    assert "Obs lorem" in desc_ciudad


def test_columns_are_canonical(request):
    """Verifica que las columnas devueltas sean las canónicas para cada banco."""
    try:
        sample_files_by_bank = request.getfixturevalue("sample_files_by_bank")
    except Exception:
        pytest.skip("sample_files_by_bank fixture no disponible")

    for banco, csv_path in sample_files_by_bank.items():
        df, detected = cargar_banco(csv_path)
        assert detected == banco
        # comparación usando _keyize para tolerancia
        exp_keys = [_keyize(c) for c in BANCOS[banco]["cols"]]
        got_keys = [_keyize(c) for c in df.columns]
        assert exp_keys == got_keys

