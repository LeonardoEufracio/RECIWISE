"""Funciones deterministas de apoyo a D3. No deciden agrupaciones."""
from datetime import datetime
from math import asin, cos, radians, sin, sqrt


def distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia geodésica aproximada (Haversine), NO distancia vial."""
    for lat in (lat1, lat2):
        if not -90 <= lat <= 90:
            raise ValueError("La latitud debe estar entre -90 y 90")
    for lon in (lon1, lon2):
        if not -180 <= lon <= 180:
            raise ValueError("La longitud debe estar entre -180 y 180")
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi, dlambda = phi2 - phi1, radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * 6_371_000 * asin(min(1, sqrt(a)))


def diferencia_horas(fecha1: datetime, fecha2: datetime) -> float:
    """Diferencia temporal absoluta entre observaciones con zona horaria."""
    if fecha1.tzinfo is None or fecha1.utcoffset() is None:
        raise ValueError("fecha1 necesita zona horaria")
    if fecha2.tzinfo is None or fecha2.utcoffset() is None:
        raise ValueError("fecha2 necesita zona horaria")
    return abs((fecha1 - fecha2).total_seconds()) / 3600
