# Jednoduchá kalkulačka

def secti(a, b):
    """Sečte dvě čísla."""
    return a + b

def odecti(a, b):
    """Odečte dvě čísla."""
    return a - b

def vynasob(a, b):
    """Vynásobí dvě čísla."""
    return a * b

def vydel(a, b):
    """Vydělí dvě čísla. Pozor na dělení nulou."""
    if b == 0:
        raise ValueError("Nelze dělit nulou")
    return a / b
