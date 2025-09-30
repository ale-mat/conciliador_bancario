from __future__ import annotations
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    title: str
    page_layout: str
    fecha_vista_formato: str


@dataclass(frozen=True)
class ConciliacionConfig:
    tolerancia_dias_default: int
    tolerancia_importe_default: float
    permitir_conciliacion_grupal: bool
    permitir_grupos_fuera_de_fecha: bool


@dataclass(frozen=True)
class LecturaConfig:
    csv_encodings: list[str]
    csv_separadores: list[str]


@dataclass(frozen=True)
class Config:
    app: AppConfig
    conciliacion: ConciliacionConfig
    lectura: LecturaConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    app = AppConfig(**data["app"])
    conc = ConciliacionConfig(**data["conciliacion"])
    lec = LecturaConfig(**data["lectura"])

    return Config(app=app, conciliacion=conc, lectura=lec)
