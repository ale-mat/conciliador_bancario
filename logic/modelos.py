from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal


Origen = Literal["Banco", "Interno"]


@dataclass(frozen=True)
class Movimiento:
    fecha: date          # fecha normalizada (día)
    importe: float       # importe final (único o C - D)
    descripcion: str     # texto libre
    origen: Origen       # "Banco" o "Interno"
    meta_origen: str = ""  # nombre de archivo/hoja opcional


@dataclass(frozen=True)
class Match:
    fecha_banco: date
    importe_banco: float
    desc_banco: str
    fecha_interno: date
    importe_interno: float
    desc_interno: str
    estado: str              # "Conciliado exacto" o "Sugerido (...)"
    correccion_sugerida: str
