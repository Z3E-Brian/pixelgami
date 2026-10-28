"""Cuánto ha jugado cada juego y cuándo fue la última vez (el registro de memoria-mcp). Solo informa."""
import re

from funciones import Pedido, Resultado, mcp

memoria = mcp("memoria")
TEMA = re.compile(r"\b(horas|cu[aá]nto (he |llevo )?jug|[uú]ltima vez que jug|cu[aá]nto llevo)", re.I)


def detectar(texto: str) -> bool:
    return bool(TEMA.search(texto))


def entender(pedido: Pedido, modelo) -> bool:
    return True  # si el router dice que es de horas de juego, el registro va siempre


def ejecutar(intencion: bool, pedido: Pedido) -> Resultado:
    return Resultado("Horas de juego registradas:\n" + memoria.horas_de_juego(), hizo=False, con_notas=True)
