# ADR 0014 · Comisiones con `Decimal` y redondeo al peso

- **Estado:** aceptada.
- **Fecha:** módulo 16; registrada el 2026-11-18.
- **Fuentes:** RF-80 a RF-86; "Cálculo y redondeo" y Precisiones de [`specs/TAREA-comisiones.md`](../../specs/TAREA-comisiones.md); `backend/apps/commissions/settlement.py` (`round_cop`, `split`), `models.py` (`_pct_field`); `backend/tests/commissions/test_settlement.py`.

## Contexto

Una comisión es dinero que se paga a personas: el asesor y, si el cliente vino de un broker, también el broker. Las partes tienen que sumar exactamente el total, el cálculo no puede variar por errores de coma flotante y una liquidación ya hecha no puede cambiar si mañana se edita el plan.

## Opciones consideradas

1. **`float`.** `0.1 + 0.2 != 0.3`: diferencias de un peso que no cuadran.
2. **Redondear cada parte por separado.** Con porcentajes como 70/30, la suma puede quedar un peso arriba o abajo del total.
3. **`Decimal` con `ROUND_HALF_UP`, redondeando el total y la parte del broker, y el asesor se lleva el resto.**

## Decisión

Opción 3. Montos en pesos enteros (`BIGINT`) y porcentajes `NUMERIC(8,4)`. `total = round(base × tasa / 100)`; con broker, `broker = round(total × porción / 100)` y `asesor = total − broker`. Sin broker, una sola parte del 100 %. La liquidación **copia** la base, la tasa, los porcentajes y el origen; es única por solicitud (índice único parcial entre las activas) y se calcula con la fila de la solicitud bloqueada.

## Consecuencias

- **A favor:** la suma siempre cuadra; cambiar o cerrar un plan nunca reescribe el pasado; un evento repetido no paga dos veces.
- **Costo:** el asesor absorbe la diferencia del redondeo (como máximo un peso). Ejemplo: desembolso de $123.456.789 al 1 % → total $1.234.568, broker $370.370, asesor $864.198.
- **Corrección del desembolso:** sin pagos, se anula y se recalcula; con alguna parte pagada, solo se marca `needs_review` (los ajustes quedan fuera de la v1).
- **Visibilidad:** ni la actividad ni la auditoría llevan montos, porque el asesor ve la actividad y no debe ver la parte del broker.
