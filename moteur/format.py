"""Mise en forme des nombres et pourcentages (usage français)."""

ESPACE = " "  # espace insécable


def n(valeur) -> str:
    """12543540 → « 12 543 540 » ; None → « / »."""
    if valeur is None:
        return "/"
    try:
        return f"{int(valeur):,}".replace(",", ESPACE)
    except (TypeError, ValueError):
        return str(valeur)


def pct(part, base, decimales: int = 1) -> str:
    if not base:
        return "–"
    v = part / base * 100
    if 0 < v < 10 ** -decimales:
        return f"<{ESPACE}0,{'0' * (decimales - 1)}1{ESPACE}%"
    return f"{v:.{decimales}f}".replace(".", ",") + f"{ESPACE}%"


def taux(part, base) -> float | None:
    return round(part / base * 100, 2) if base else None
