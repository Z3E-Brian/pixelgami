"""El estado del PC (RAM, disco, CPU, GPU, temperaturas, cuánto usa la asistente), con acciones-mcp. Solo informa."""
import re

from funciones import Pedido, Resultado, mcp

acciones = mcp("acciones")
TEMA = re.compile(r"\b((ram|discos?|gigas?|gb|megas?|mb|lag|swap|zram|cpu|gpu|vram)\b|memoria|temperatur|calor|caliente|espacio|almacenamiento|consum|procesador|gr[aá]fica|rendimiento|lent[oa]|pesad[oa]|encendid)", re.I)


def detectar(texto: str) -> bool:
    return bool(TEMA.search(texto))


def entender(pedido: Pedido, modelo) -> bool:
    return True  # si el router dice que es del PC, el estado va siempre (no hay nada que interpretar)


def ejecutar(intencion: bool, pedido: Pedido) -> Resultado:
    return Resultado("Estado actual del PC:\n" + acciones.estado_sistema(), hizo=False, con_notas=True)
