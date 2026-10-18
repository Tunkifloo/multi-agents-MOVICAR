// contrato.js · Contrato de entrada de MOVICAR (Lab 02, v3) + clave de idempotencia.
// FUENTE ÚNICA: n8n_deploy.py copia esta función en validar_solicitud y en sw_registrar_solicitud.
// No editar la copia dentro de los JSON; editar este archivo y volver a desplegar.
// Constantes inyectadas por el despliegue: __DIAS_MAX_ANTICIPACION__

function validarContrato(q, ahora) {
  q = q || {};
  const DIAS_MAX = Number('__DIAS_MAX_ANTICIPACION__') || 60;
  const errores = [];
  const ref = ahora ? new Date(ahora) : new Date();
  const hoy = ref.toLocaleDateString('en-CA', { timeZone: 'America/Lima' });

  // teléfono
  let tel = String(q.telefono || '').replace(/[\s\-().]/g, '');
  if (/^9\d{8}$/.test(tel)) tel = '+51' + tel;
  else if (/^51\d{9}$/.test(tel)) tel = '+' + tel;
  if (!/^\+\d{10,15}$/.test(tel)) errores.push('telefono: se necesita un celular válido de 9 dígitos (ej. 987 654 321)');

  // placa (Perú: 6 alfanuméricos)
  let placa = String(q.placa || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!/^[A-Z0-9]{6}$/.test(placa)) errores.push('placa: debe tener 6 caracteres (ej. ABC-123)');
  else placa = placa.slice(0, 3) + '-' + placa.slice(3);

  // vehículo
  const vehiculo = String(q.vehiculo || '').trim();
  if (vehiculo.length < 3 || vehiculo.length > 80) errores.push('vehiculo: indique marca, modelo y año');

  // fecha
  const fecha = String(q.fecha_deseada || '').trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || isNaN(Date.parse(fecha + 'T12:00:00Z'))) {
    errores.push('fecha_deseada: falta una fecha válida (AAAA-MM-DD)');
  } else {
    const dHoy = Date.parse(hoy + 'T12:00:00Z');
    const dFecha = Date.parse(fecha + 'T12:00:00Z');
    const dias = Math.round((dFecha - dHoy) / 86400000);
    if (dias < 0) errores.push('fecha_deseada: no puede ser anterior a hoy (' + hoy + ')');
    else if (dias > DIAS_MAX) errores.push('fecha_deseada: solo agendamos hasta ' + DIAS_MAX + ' días adelante');
    else if (new Date(dFecha).getUTCDay() === 0) errores.push('fecha_deseada: los domingos no atendemos');
  }

  // descripción
  const desc = String(q.descripcion_falla || '').trim();
  if (!desc) errores.push('descripcion_falla: falta el servicio o síntoma');
  else if (desc.length > 500) errores.push('descripcion_falla: máximo 500 caracteres');

  // kilometraje
  let km = Number(q.kilometraje);
  if (!Number.isFinite(km) || km < 0) km = 0;

  const valido = errores.length === 0;
  return {
    valido,
    errores,
    clave: valido ? calcularClave(tel, placa, fecha) : '',
    datos: { telefono: tel, placa, vehiculo, kilometraje: Math.round(km), fecha_deseada: fecha, descripcion_falla: desc },
  };
}

// Clave de negocio: teléfono | placa | fecha. Sin tipo_servicio (lo infiere la IA), sin marcas de tiempo ni IDs.
function calcularClave(tel, placa, fecha) {
  const material = [tel, placa, fecha].join('|').toLowerCase();
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < material.length; i++) {
    const ch = material.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 'MV-' + (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
}

if (typeof module !== 'undefined') module.exports = { validarContrato, calcularClave };
