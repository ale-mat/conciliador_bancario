import logging
from typing import Optional


_logger: Optional[logging.Logger] = None


def get_logger(name: str = "conciliador") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _logger = logger
    return logger
