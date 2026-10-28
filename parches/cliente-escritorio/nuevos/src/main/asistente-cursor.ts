import { BrowserWindow } from "electron";
import net from "net";
import path from "path";

/**
 * Asistente: en Wayland/XWayland la app solo ve el ratón cuando está encima de su
 * ventana. Para que Asistente siga el cursor por toda la pantalla se le pregunta a
 * Hyprland por su socket (cursorpos) y se manda al renderer la posición relativa
 * a la ventana ("asistente-cursor"), solo mientras está visible.
 */
const CADA_MS = 50;
const VENTANA_CADA_MS = 1000;

function pedir(socket: string, orden: string): Promise<string> {
  return new Promise((resolve) => {
    const c = net.createConnection(socket);
    let datos = "";
    c.on("connect", () => c.write(orden));
    c.on("data", (b) => { datos += b; });
    c.on("end", () => resolve(datos));
    c.on("error", () => resolve(""));
  });
}

export function seguirCursorHyprland(window: BrowserWindow): void {
  const firma = process.env.HYPRLAND_INSTANCE_SIGNATURE;
  const dir = process.env.XDG_RUNTIME_DIR;
  if (process.platform !== "linux" || !firma || !dir) return;
  const socket = path.join(dir, "hypr", firma, ".socket.sock");

  let origen: { x: number, y: number } | null = null; // esquina de la ventana; null = oculta
  let ultimo = "";

  const ventana = async () => {
    try {
      const clientes = JSON.parse((await pedir(socket, "j/clients")) || "[]");
      const c = clientes.find((v: any) => v.class === "open-llm-vtuber");
      origen = c && !String(c.workspace?.name).startsWith("special")
        ? { x: c.at[0], y: c.at[1] }
        : null;
    } catch {
      origen = null;
    }
  };

  const cursor = async () => {
    if (!origen || window.isDestroyed()) return;
    try {
      const p = JSON.parse((await pedir(socket, "j/cursorpos")) || "null");
      if (!p || !origen) return;
      const rel = { x: p.x - origen.x, y: p.y - origen.y };
      const clave = `${rel.x},${rel.y}`;
      if (clave !== ultimo) {
        ultimo = clave;
        window.webContents.send("asistente-cursor", rel);
      }
    } catch {
      // respuesta incompleta: se ignora este ciclo
    }
  };

  ventana();
  setInterval(ventana, VENTANA_CADA_MS);
  setInterval(cursor, CADA_MS);
}
