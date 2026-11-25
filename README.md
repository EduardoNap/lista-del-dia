# Lista del día

Cada mañana le dice al equipo de asesores a quién llamar primero y por qué.

**Ver la lista:** https://eduardonap.github.io/lista-del-dia/lista_hoy.html

## Cómo funciona

- Lee `leads_ficticios.csv` y `gasto_por_canal.csv`.
- Cada asesor recibe dos listas: hasta 12 personas a las que nadie ha llamado y 3 de seguimiento.
- Dentro de cada lista va primero quien suma más puntos (qué tan reciente es, por qué canal llegó, si ya mostró interés), y cada persona trae la razón de su lugar.

## Cómo generar la lista

Necesita Python 3 y pandas.

```
python3 lista_del_dia.py
```

Escribe `lista_hoy.html`. La fecha simulada es el lunes 9 de noviembre de 2026 a las 9:00. Para otra mañana:

```
python3 lista_del_dia.py "2026-10-20 09:00"
```

Los cupos y los puntos se cambian al inicio de `lista_del_dia.py`.
