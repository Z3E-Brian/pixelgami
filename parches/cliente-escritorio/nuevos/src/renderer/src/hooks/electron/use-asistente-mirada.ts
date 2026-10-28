import { useEffect } from 'react';
import { cajaCabeza, caricia } from '@/utils/asistente-cabeza';

const ALCANCE_PX = 450; // a esta distancia de la cabeza ya gira lo máximo
const GIRO_MAX = 0.7; // fracción del giro del modelo (1 = 30° de cabeza)

/**
 * Asistente: mira hacia el cursor en toda la pantalla. La posición llega del proceso
 * principal (asistente-cursor.ts, vía Hyprland) relativa a la ventana, aunque esté fuera.
 */
export function useAsistenteMirada(activa: boolean) {
  useEffect(() => {
    const api = window.api as any;
    if (!activa || !api?.onAsistenteCursor) return undefined;
    let centro: { x: number, y: number } | null = null;
    const actualizarCentro = () => {
      const c = cajaCabeza();
      centro = c ? { x: (c.x0 + c.x1) / 2, y: (c.y0 + c.y1) / 2 } : null;
    };
    actualizarCentro();
    const timer = setInterval(actualizarCentro, 2000);
    const limita = (v: number) => Math.max(-1, Math.min(1, v)) * GIRO_MAX;

    const cleanup = api.onAsistenteCursor(({ x, y }: { x: number, y: number }) => {
      const model = (window as any).getLAppAdapter?.()?.getModel?.();
      if (!model || caricia.activa) return; // mientras la acarician, la cabeza sigue la mano
      const c = centro || { x: window.innerWidth / 2, y: window.innerHeight / 2 };
      model.setDragging(limita((x - c.x) / ALCANCE_PX), limita((c.y - y) / ALCANCE_PX));
    });
    return () => {
      clearInterval(timer);
      cleanup?.();
    };
  }, [activa]);
}
