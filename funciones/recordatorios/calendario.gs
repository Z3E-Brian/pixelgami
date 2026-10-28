// Puente entre la asistente y tu Google Calendar (se pega en script.google.com y se publica como "Aplicación web").
// Corre con tu cuenta: solo sabe leer eventos y crear nuevos en tu calendario principal. Nunca borra ni edita.
// La clave la pone google_calendario.py al copiarlo; sin ella no responde a nadie.
const CLAVE = '__CLAVE__';

function doGet(e) { return responder(e.parameter); }
function doPost(e) { return responder(JSON.parse(e.postData.contents)); }

function responder(p) {
  if (p.clave !== CLAVE) return salida({ error: 'clave incorrecta' });
  const cal = CalendarApp.getDefaultCalendar();
  const zona = cal.getTimeZone();
  if (p.accion === 'eventos') {
    const eventos = cal.getEvents(new Date(p.desde), new Date(p.hasta)).map(ev => ({
      titulo: ev.getTitle(),
      todo_el_dia: ev.isAllDayEvent(),
      inicio: ev.isAllDayEvent()
        ? Utilities.formatDate(ev.getAllDayStartDate(), zona, "yyyy-MM-dd'T'00:00:00")
        : ev.getStartTime().toISOString(),
      lugar: ev.getLocation(),
    }));
    return salida({ eventos: eventos });
  }
  if (p.accion === 'apuntar') {
    const opciones = { description: p.descripcion || '' };
    const inicio = new Date(p.inicio), fin = new Date(p.fin);
    let regla = null;
    if (p.dias) {
      const nombres = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];
      regla = CalendarApp.newRecurrence().addWeeklyRule()
        .onlyOnWeekdays(p.dias.map(d => CalendarApp.Weekday[nombres[d]]));
    } else if (p.dia_mes) {
      regla = CalendarApp.newRecurrence().addMonthlyRule().onlyOnMonthDay(p.dia_mes);
    }
    let ev;
    if (p.todo_el_dia) {
      ev = regla ? cal.createAllDayEventSeries(p.titulo, inicio, regla, opciones)
                 : cal.createAllDayEvent(p.titulo, inicio, opciones);
    } else {
      ev = regla ? cal.createEventSeries(p.titulo, inicio, fin, regla, opciones)
                 : cal.createEvent(p.titulo, inicio, fin, opciones);
    }
    return salida({ ok: true, id: ev.getId() });
  }
  return salida({ error: 'acción desconocida' });
}

function salida(datos) {
  return ContentService.createTextOutput(JSON.stringify(datos)).setMimeType(ContentService.MimeType.JSON);
}
