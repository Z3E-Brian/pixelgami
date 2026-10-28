import { RefObject, useEffect } from 'react';

type Rect = { x: number, y: number, width: number, height: number };

const FRANJA = 20; // alto en px de cada franja de la silueta
const MARGEN = 6; // holgura en px alrededor de Asistente
const CADA_MS = 250;

/**
 * Asistente: en Linux la ventana mascota solo recibe clics dentro de la forma que se le
 * pasa a window.setShape; lo demás deja pasar el clic a lo que está detrás.
 * La forma es la silueta de Asistente (franjas horizontales que siguen el ancho de lo
 * dibujado, así sigue el movimiento y el arrastre) más el cuadro de texto.
 */
export function useAsistenteForma(boxRef: RefObject<HTMLElement>, boxVisible: boolean) {
  useEffect(() => {
    const api = window.api as any;
    if (!api?.setAsistenteShape) return undefined;
    let ultima = '';

    const timer = setInterval(() => {
      if (document.hidden) return;
      const rects: Rect[] = [];

      const box = boxRef.current?.getBoundingClientRect();
      if (boxVisible && box && box.width > 0) {
        rects.push({
          x: Math.max(0, Math.floor(box.left)),
          y: Math.max(0, Math.floor(box.top)),
          width: Math.ceil(box.width),
          height: Math.ceil(box.height),
        });
      }

      const model = (window as any).getLAppAdapter?.()?.getModel?.();
      const core = model?._model;
      const m: Float32Array | null = model?._mvpArray;
      if (core && m) {
        const W = window.innerWidth;
        const H = window.innerHeight;
        const franjas = new Map<number, [number, number]>();
        for (let d = 0; d < core.getDrawableCount(); d++) {
          if (!core.getDrawableDynamicFlagIsVisible(d) || core.getDrawableOpacity(d) < 0.1) continue;
          const v: Float32Array = core.getDrawableVertices(d);
          for (let i = 0; i < v.length; i += 2) {
            const x = ((m[0] * v[i] + m[4] * v[i + 1] + m[12] + 1) / 2) * W;
            const y = ((1 - (m[1] * v[i] + m[5] * v[i + 1] + m[13])) / 2) * H;
            if (y < 0 || y >= H) continue;
            const f = Math.floor(y / FRANJA);
            const r = franjas.get(f);
            if (r) {
              r[0] = Math.min(r[0], x);
              r[1] = Math.max(r[1], x);
            } else {
              franjas.set(f, [x, x]);
            }
          }
        }
        franjas.forEach(([x0, x1], f) => {
          const izq = Math.max(0, Math.floor(x0 - MARGEN));
          const der = Math.min(W, Math.ceil(x1 + MARGEN));
          if (der > izq) rects.push({ x: izq, y: f * FRANJA, width: der - izq, height: FRANJA });
        });
      }

      const clave = JSON.stringify(rects);
      if (clave !== ultima) {
        ultima = clave;
        api.setAsistenteShape(rects);
      }
    }, CADA_MS);

    return () => clearInterval(timer);
  }, [boxRef, boxVisible]);
}
