/**
 * Asistente: zonas de la cara en pantalla y reacciones al tocarlas.
 * La cabeza sale de las partes del modelo (la primera de partesCabeza con algo
 * visible), un poco ampliada hacia arriba para incluir el pelo y los adornos.
 * Zonas (fracciones de esa caja, calibradas con Ink Asistente): arriba hasta las cejas =
 * cabeza; a los lados bajo los ojos = mejillas; ojos, nariz y boca = nada, para que
 * no se confundan.
 */

const DURACION_TOQUE_MS = 2000;
// Partes de la cabeza y expresiones de cada toque: las da el modelo en model_dict.json ("partesCabeza",
// "toques"); sin eso, las de Ink Asistente y el nombre estándar PartFace (Mao y muchos otros)
const PARTES_POR_DEFECTO = ['head2', 'head', 'PartHead', 'PartFace'];
const TOQUES_POR_DEFECTO = { cabeza: 'uwu', mejilla: 'guino_a', caricia: 'acariciada' };
let partesCabeza = PARTES_POR_DEFECTO;
let EXPRESION = { ...TOQUES_POR_DEFECTO };

/** La llama live2d-config-context al cambiar de modelo */
export function configurarCabeza(partes?: string[], toques?: Partial<typeof TOQUES_POR_DEFECTO>): void {
  partesCabeza = partes?.length ? partes : PARTES_POR_DEFECTO;
  EXPRESION = { ...TOQUES_POR_DEFECTO, ...toques };
}

export type Caja = { x0: number, y0: number, x1: number, y1: number };

/** Caja de la cabeza en px de la ventana, o null si el modelo no tiene esas partes */
export function cajaCabeza(): Caja | null {
  const model = (window as any).getLAppAdapter?.()?.getModel?.();
  const core = model?._model;
  const m: Float32Array | null = model?._mvpArray;
  const partes = core?._model?.parts;
  if (!core || !m || !partes) return null;

  const W = window.innerWidth;
  const H = window.innerHeight;
  for (const nombre of partesCabeza) {
    const desciende = (pi: number): boolean => {
      for (let p = pi; p >= 0; p = partes.parentIndices[p]) {
        if (partes.ids[p] === nombre) return true;
      }
      return false;
    };
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    for (let d = 0; d < core.getDrawableCount(); d++) {
      if (!core.getDrawableDynamicFlagIsVisible(d) || core.getDrawableOpacity(d) < 0.1) continue;
      if (!desciende(core.getDrawableParentPartIndex(d))) continue;
      const v: Float32Array = core.getDrawableVertices(d);
      for (let i = 0; i < v.length; i += 2) {
        const x = ((m[0] * v[i] + m[4] * v[i + 1] + m[12] + 1) / 2) * W;
        const y = ((1 - (m[1] * v[i] + m[5] * v[i + 1] + m[13])) / 2) * H;
        x0 = Math.min(x0, x);
        x1 = Math.max(x1, x);
        y0 = Math.min(y0, y);
        y1 = Math.max(y1, y);
      }
    }
    if (x1 > x0) return { x0, y0: y0 - (y1 - y0) * 0.1, x1, y1 };
  }
  return null;
}

export type Zona = 'cabeza' | 'mejilla' | null;

/** Qué parte de la cara hay en (x, y), en px de la ventana */
export function zonaToque(x: number, y: number): Zona {
  const c = cajaCabeza();
  if (!c || x < c.x0 || x > c.x1 || y < c.y0 || y > c.y1) return null;
  const fy = (y - c.y0) / (c.y1 - c.y0);
  const fx = Math.abs(x - (c.x0 + c.x1) / 2) / (c.x1 - c.x0);
  if (fy <= 0.51) return 'cabeza';
  if (fy >= 0.68 && fy <= 0.9 && fx >= 0.12 && fx <= 0.3) return 'mejilla';
  return null;
}

const reaccion = {
  anterior: null as string | null, // expresión a la que volver
  timer: undefined as ReturnType<typeof setTimeout> | undefined,
  enCurso: false, // hay un toque (uwu/guiño) mostrándose
};

function adaptador() {
  const adapter = (window as any).getLAppAdapter?.();
  const model = adapter?.getModel?.();
  if (!adapter || !model) return null;
  const nombres: string[] = Array.from({ length: adapter.getExpressionCount() }, (_, i) => adapter.getExpressionName(i));
  return { adapter, model, nombres };
}

function poner(nombre: string): boolean {
  const a = adaptador();
  if (!a || !a.nombres.includes(nombre)) return false;
  clearTimeout(reaccion.timer);
  const actual = a.model._currentExpression;
  if (!Object.values(EXPRESION).includes(actual)) reaccion.anterior = actual;
  a.adapter.setExpression(nombre);
  return true;
}

function volverEn(ms: number, nombre: string): void {
  clearTimeout(reaccion.timer);
  reaccion.timer = setTimeout(() => {
    reaccion.enCurso = false;
    const a = adaptador();
    // si entretanto cambió de ánimo (respuesta nueva), no pisarlo
    if (a && a.model._currentExpression === nombre) {
      a.adapter.setExpression(reaccion.anterior || a.nombres[0]);
    }
  }, ms);
}

/** Toque corto: cabeza = uwu, mejilla = guiño; unos segundos y vuelve a la cara que tenía */
export function reaccionarToque(zona: Zona): void {
  if (!zona) return;
  const nombre = EXPRESION[zona];
  if (poner(nombre)) {
    reaccion.enCurso = true;
    volverEn(DURACION_TOQUE_MS, nombre);
  }
}

/**
 * La conversación quiere poner una expresión: si hay una caricia o un toque en curso
 * se guarda para después (devuelve true) en vez de cortar la reacción.
 */
export function retenerExpresion(nombre: string | null | undefined): boolean {
  if (!caricia.activa && !reaccion.enCurso) return false;
  if (nombre) reaccion.anterior = nombre;
  return true;
}

/**
 * Caricia (mantener presionada la cabeza, o frotarla): ojos cerrados felices y la
 * cabeza se recuesta hacia la mano mientras el clic siga apretado; al soltar vuelve
 * a la cara que tenía. Mientras dura, la mirada deja de seguir el cursor.
 */
export const caricia = {
  activa: false,
  empezar(): void {
    caricia.activa = poner(EXPRESION.caricia) || poner(EXPRESION.cabeza);
  },
  mover(x: number): void {
    if (!caricia.activa) return;
    const c = cajaCabeza();
    const model = (window as any).getLAppAdapter?.()?.getModel?.();
    if (!c || !model) return;
    const dx = Math.max(-1, Math.min(1, (x - (c.x0 + c.x1) / 2) / ((c.x1 - c.x0) / 2)));
    model.setDragging(dx * 0.45, -0.3);
  },
  terminar(): void {
    if (!caricia.activa) return;
    caricia.activa = false;
    volverEn(0, EXPRESION.caricia);
  },
};
