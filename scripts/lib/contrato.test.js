// Pruebas del contrato: node scripts/lib/contrato.test.js
const assert = require('assert');
const { validarContrato } = require('./contrato.js');
const AHORA = '2026-10-17T15:00:00Z'; // sábado 17/10/2026, 10:00 Lima
const base = { telefono: '987 654 321', placa: 'bxr742', vehiculo: 'Toyota Yaris 2020', kilometraje: 10000, fecha_deseada: '2026-10-19', descripcion_falla: 'Mantenimiento de 10 000 km' };
let n = 0; const t = (nombre, fn) => { fn(); n++; console.log('ok -', nombre); };

t('caso válido normaliza', () => {
  const r = validarContrato(base, AHORA);
  assert.strictEqual(r.valido, true, r.errores.join());
  assert.strictEqual(r.datos.telefono, '+51987654321');
  assert.strictEqual(r.datos.placa, 'BXR-742');
  assert.match(r.clave, /^MV-[0-9a-f]{16}$/);
});
t('clave estable ante formato distinto', () => {
  const a = validarContrato(base, AHORA).clave;
  const b = validarContrato({ ...base, telefono: '+51 987-654-321', placa: 'BXR-742', descripcion_falla: 'otra redacción' }, AHORA).clave;
  assert.strictEqual(a, b);
});
t('clave cambia con otra fecha', () => {
  assert.notStrictEqual(validarContrato(base, AHORA).clave, validarContrato({ ...base, fecha_deseada: '2026-10-20' }, AHORA).clave);
});
t('teléfono corto', () => assert.ok(validarContrato({ ...base, telefono: '98765' }, AHORA).errores.some(e => e.startsWith('telefono'))));
t('placa inválida', () => assert.ok(validarContrato({ ...base, placa: 'AB' }, AHORA).errores.some(e => e.startsWith('placa'))));
t('placa de 7 rechazada', () => assert.ok(validarContrato({ ...base, placa: 'ABC1234' }, AHORA).errores.some(e => e.startsWith('placa'))));
t('fecha pasada', () => assert.ok(validarContrato({ ...base, fecha_deseada: '2026-10-01' }, AHORA).errores.some(e => e.includes('anterior'))));
t('domingo', () => assert.ok(validarContrato({ ...base, fecha_deseada: '2026-10-18' }, AHORA).errores.some(e => e.includes('domingo'))));
t('más de 60 días', () => assert.ok(validarContrato({ ...base, fecha_deseada: '2027-03-01' }, AHORA).errores.some(e => e.includes('60'))));
t('hoy es válido', () => assert.strictEqual(validarContrato({ ...base, fecha_deseada: '2026-10-17' }, AHORA).valido, true));
t('reporta todos los errores juntos', () => {
  const r = validarContrato({ telefono: '1', placa: 'x', vehiculo: '', fecha_deseada: 'mañana', descripcion_falla: '' }, AHORA);
  assert.strictEqual(r.errores.length, 5); assert.strictEqual(r.clave, '');
});
t('kilometraje inválido → 0', () => assert.strictEqual(validarContrato({ ...base, kilometraje: -5 }, AHORA).datos.kilometraje, 0));
console.log(`\n${n} pruebas OK`);
