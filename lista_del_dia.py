""" Lista de cada mañana para los asesores

Uso:
    python3 lista_del_dia.py                       # mañana simulada
    python3 lista_del_dia.py "2026-10-20 09:00"    # cualquier otra mañana

Lee leads_ficticios.csv y gasto_por_canal.csv y escribe lista_hoy.html.
"""
import sys
from html import escape
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).parent

## Configuración

HOY = pd.Timestamp('2026-11-09 09:00')
ASESORES = ['Asesor A', 'Asesor B', 'Asesor C', 'Asesor D', 'Asesor E']

CUPO_PRIMERAS = 12       # personas que nadie ha llamado
CUPO_SEGUIMIENTO = 3     # personas en seguimiento o que no contestaron

GRUPO = {'sin_contactar':  'Primeras llamadas',
         'en_seguimiento': 'Seguimiento',
         'no_contesta':    'Seguimiento'}

# Dentro de cada lista va primero quien suma más puntos.
PUNTOS = {
    'Llegó en las últimas 24 horas':     30,
    'Está en seguimiento':               15,
    'Hablamos hace 7 días o menos':      30,
    'No contestó hace 14 días o menos':   5,
}

# Salen del modelo 
PUNTOS_CANAL = {'Google': 20, 'Referido': 20, 'Organico': 10, 'Meta': 10, 'TikTok': 0}

FRASE_CANAL = {
    'Google':   'Nos buscó en Google, el canal donde más gente compra.',
    'Referido': 'Viene recomendado, y los recomendados compran mucho.',
}

# Si una persona se registró varias veces, se queda con su resultado más avanzado.
MEJOR_RESULTADO = {'venta': 0, 'en_seguimiento': 1, 'no_interesado': 2,
                   'no_contesta': 3, 'sin_contactar': 4}
ABIERTOS = list(GRUPO) 


## Limpieza

def parse_fecha(s):
    """Las fechas vienen en dos formatos"""
    iso = pd.to_datetime(s, format='%Y-%m-%d %H:%M', errors='coerce')
    ddmm = pd.to_datetime(s, format='%d/%m/%Y %H:%M', errors='coerce')
    return iso.fillna(ddmm)


def cargar_personas(hoy=HOY):
    """Lee los leads, los limpia y devuelve una fila por persona, vista desde hoy."""
    df = pd.read_csv(CARPETA / 'leads_ficticios.csv', dtype={'telefono': str})
    df['fecha_registro'] = parse_fecha(df['fecha_registro'])
    df['primer_contacto'] = parse_fecha(df['primer_contacto'])

    df['persona'] = df.groupby(['telefono', 'estado', 'edad', 'objetivo']).ngroup()

    # Edades imposibles (0, 140, 199) quedan como "sin dato".
    df['edad'] = df['edad'].where(df['edad'].between(18, 90))

    # Foto de la mañana, lo que pasó después de hoy todavía no ha pasado.
    df = df[df['fecha_registro'] <= hoy].copy()
    despues = df['primer_contacto'] > hoy
    df.loc[despues, 'resultado'] = 'sin_contactar'
    df.loc[despues, 'asesor'] = None
    df.loc[despues, 'primer_contacto'] = pd.NaT
    df.loc[despues, 'monto_venta'] = None

    # De registros a personas.
    por_persona = df.groupby('persona')
    df['n_registros'] = por_persona['lead_id'].transform('size')
    df['primer_registro'] = por_persona['fecha_registro'].transform('min')
    df['ultimo_registro'] = por_persona['fecha_registro'].transform('max')
    df['_orden'] = df['resultado'].map(MEJOR_RESULTADO)
    personas = (df.sort_values(['persona', '_orden', 'fecha_registro'])
                  .drop_duplicates('persona')
                  .drop(columns='_orden'))

    # Tiempos, contados desde hoy.
    dia = hoy.normalize()
    personas['dias_espera'] = (dia - personas['primer_registro'].dt.normalize()).dt.days
    personas['horas_desde_registro'] = (hoy - personas['ultimo_registro']).dt.total_seconds() / 3600
    personas['dias_desde_contacto'] = (dia - personas['primer_contacto'].dt.normalize()).dt.days
    personas['horas_a_contacto'] = (personas['primer_contacto'] - personas['fecha_registro']).dt.total_seconds() / 3600
    return personas


## Puntuación

def hace(dias):
    if dias <= 0:
        return 'hoy'
    if dias == 1:
        return 'ayer'
    return f'hace {int(dias)} días'


def puntuar(p, puntos=PUNTOS, puntos_canal=PUNTOS_CANAL):
    """Recibe una persona y devuelve (puntos, por qué). Una regla por bloque."""
    total, razones = 0, []

    if p['resultado'] == 'sin_contactar':
        razones.append(f"Nadie le ha llamado desde que pidió información {hace(p['dias_espera'])}.")

    if p['resultado'] == 'en_seguimiento':
        total += puntos['Está en seguimiento']
        razones.append(f"Ya mostró interés: hablamos con esta persona {hace(p['dias_desde_contacto'])}.")
        if p['dias_desde_contacto'] <= 7:
            total += puntos['Hablamos hace 7 días o menos']
            razones.append('La conversación sigue fresca.')

    if p['resultado'] == 'no_contesta':
        if p['dias_desde_contacto'] <= 14:
            total += puntos['No contestó hace 14 días o menos']
            razones.append(f"No contestó {hace(p['dias_desde_contacto'])}; vale un reintento.")
        else:
            razones.append(f"No contestó {hace(p['dias_desde_contacto'])}.")

    if p['horas_desde_registro'] <= 24:
        total += puntos['Llegó en las últimas 24 horas']
        razones.append(f"Es reciente: llegó hace {max(int(p['horas_desde_registro']), 1)} horas.")

    total += puntos_canal.get(p['canal'], 0)
    if p['canal'] in FRASE_CANAL:
        razones.append(FRASE_CANAL[p['canal']])

    if p['n_registros'] > 1:
        razones.append(f"Pidió información {p['n_registros']} veces.")

    return total, ' '.join(razones)


## Ordenar y repartir

def armar_cola(personas, puntos=PUNTOS, puntos_canal=PUNTOS_CANAL):
    """Todas las personas pendientes, ordenadas, cada una con su grupo, su asesor y su lugar."""
    cola = personas[personas['resultado'].isin(ABIERTOS)].copy()
    cola['grupo'] = cola['resultado'].map(GRUPO)

    resultado = cola.apply(puntuar, axis=1, puntos=puntos, puntos_canal=puntos_canal)
    cola['puntos'] = [r[0] for r in resultado]
    cola['por_que'] = [r[1] for r in resultado]

    # Más puntos primero. 
    cola['desempate'] = cola['dias_espera'].astype(float).where(cola['grupo'] == 'Primeras llamadas',
                                                                -cola['dias_desde_contacto'])
    cola = cola.sort_values(['puntos', 'desempate'], ascending=False, kind='stable')

    # Quien no tiene asesor se reparte parejo, por turnos.
    sin_asesor = cola['asesor'].isna()
    cola.loc[sin_asesor, 'asesor'] = [ASESORES[i % len(ASESORES)] for i in range(sin_asesor.sum())]

    # Lugar de cada persona dentro de su asesor y su grupo.
    cola['lugar'] = cola.groupby(['asesor', 'grupo']).cumcount() + 1
    return cola


def elegir_del_dia(cola, cupo_primeras=CUPO_PRIMERAS, cupo_seguimiento=CUPO_SEGUIMIENTO):
    """La lista de hoy: los primeros de cada grupo, según los cupos de cada asesor."""
    primeras = cola[(cola['grupo'] == 'Primeras llamadas') & (cola['lugar'] <= cupo_primeras)]

    # Si a un asesor no le alcanzan las primeras llamadas, esos lugares pasan a seguimiento.
    sobran = cupo_primeras - primeras.groupby('asesor').size().reindex(ASESORES, fill_value=0)
    limite = cupo_seguimiento + cola['asesor'].map(sobran)
    seguimiento = cola[(cola['grupo'] == 'Seguimiento') & (cola['lugar'] <= limite)]

    return pd.concat([primeras, seguimiento])


## Costo por lead

def costo_por_lead():
    """Pesos de anuncios por cada lead, por canal. Referido y Orgánico cuestan 0."""
    gasto = pd.read_csv(CARPETA / 'gasto_por_canal.csv').groupby('canal')['gasto_mxn'].sum()
    leads = pd.read_csv(CARPETA / 'leads_ficticios.csv')['canal'].value_counts()
    return (gasto / leads).fillna(0)


## HTML

DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

ESTILO = """
:root { --tinta:#14262b; --suave:#566b70; --linea:#d3dddb; --fondo:#f3f6f5;
        --papel:#ffffff; --acento:#0e6b74; --espera:#a34a06; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta);
       font:16px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif; }
main { max-width:60rem; margin:0 auto; padding:2.5rem 1.25rem 4rem; }
.fecha { color:var(--suave); margin:0; }
h1 { font-size:clamp(1.9rem,5vw,3rem); line-height:1.1; font-weight:700;
     letter-spacing:-0.02em; margin:.4rem 0 1rem; max-width:22ch; text-wrap:balance; }
.resumen { max-width:62ch; margin:0 0 1.5rem; }
nav { display:flex; flex-wrap:wrap; gap:.5rem; margin-bottom:2.5rem; }
nav a { color:var(--acento); background:var(--papel); border:1px solid var(--linea);
        border-radius:2rem; padding:.3rem .9rem; text-decoration:none; font-weight:600; }
nav a:focus-visible, .tel:focus-visible { outline:3px solid var(--acento); outline-offset:2px; }
h2 { font-size:1.4rem; margin:2.5rem 0 .25rem; }
h3 { font-size:1rem; margin:1.25rem 0 .5rem; }
.cuenta { color:var(--suave); margin:0 0 .75rem; }
ol { list-style:none; margin:0; padding:0; background:var(--papel);
     border:1px solid var(--linea); border-radius:.5rem; }
li { display:grid; grid-template-columns:2.2rem 6.5rem 15rem 1fr; gap:1rem;
     padding:.9rem 1rem; border-top:1px solid var(--linea); align-items:start; }
li:first-child { border-top:0; }
.lugar { color:var(--suave); font-variant-numeric:tabular-nums; }
.espera { color:var(--espera); font-weight:700; line-height:1.2; }
.espera small { display:block; font-weight:400; color:var(--suave); }
.tel { color:var(--tinta); font-weight:700; font-size:1.1rem; text-decoration:none;
       font-variant-numeric:tabular-nums; }
.perfil { color:var(--suave); font-size:.92rem; margin:0; }
.porque { margin:0; }
.puntos { color:var(--suave); font-size:.85rem; }
footer { margin-top:3rem; color:var(--suave); max-width:62ch; }
footer table { border-collapse:collapse; margin:.5rem 0 1rem; }
footer td { padding:.15rem 1.5rem .15rem 0; }
@media (max-width:720px) {
  li { grid-template-columns:2rem 1fr; }
  .espera, .quien, .porque { grid-column:2; }
}
@media print {
  body { background:#fff; font-size:11pt; } nav { display:none; }
  section { break-before:page; } section:first-of-type { break-before:auto; }
  li { break-inside:avoid; }
}
"""


def fila_html(p):
    edad = f"{int(p['edad'])} años" if pd.notna(p['edad']) else 'edad sin dato'
    perfil = f"{edad}, {p['objetivo']}, plan de ${int(p['plan_de_interes']):,}"
    donde = f"{p['estado']}, llegó por {p['canal']}"
    tel = escape(p['telefono'])
    if p['resultado'] == 'sin_contactar':
        dias, nota = int(p['dias_espera']), 'sin llamada'
    else:
        dias, nota = int(p['dias_desde_contacto']), 'desde que le llamamos'
    cuanto = '1 día' if dias == 1 else f'{dias} días'
    espera = f"{cuanto}<small>{nota}</small>"
    return f"""<li>
  <span class="lugar">{int(p['lugar'])}</span>
  <span class="espera">{espera}</span>
  <div class="quien"><a class="tel" href="tel:{tel.replace('-', '')}">{tel}</a>
    <p class="perfil">{escape(perfil)}<br>{escape(donde)}</p></div>
  <p class="porque">{escape(p['por_que'])} <span class="puntos">({int(p['puntos'])} puntos)</span></p>
</li>"""


def escribir_html(lista, cola, hoy=HOY, archivo='lista_hoy.html'):
    sin_llamada = cola[cola['resultado'] == 'sin_contactar']
    costo = sin_llamada['canal'].map(costo_por_lead()).sum()
    fecha = f"{DIAS[hoy.dayofweek]} {hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"

    if len(sin_llamada):
        titulo = f"{len(sin_llamada)} personas siguen esperando su primera llamada"
        resumen = (f"Cada asesor tiene hoy hasta {CUPO_PRIMERAS} primeras llamadas "
                   f"y {CUPO_SEGUIMIENTO} de seguimiento. "
                   f"Quien más ha esperado lleva {int(sin_llamada['dias_espera'].max())} días. "
                   f"Traer a quienes siguen sin llamada costó ${costo:,.0f} en anuncios.")
    else:
        titulo = "Nadie está esperando su primera llamada"
        resumen = f"Hoy la lista tiene {len(lista)} personas para dar seguimiento."

    secciones, enlaces = [], []
    for asesor in ASESORES:
        suyos = lista[lista['asesor'] == asesor]
        pendientes = (cola['asesor'] == asesor).sum()
        ancla = asesor.replace(' ', '-').lower()
        enlaces.append(f'<a href="#{ancla}">{escape(asesor)}</a>')
        bloques = ''
        for grupo in ['Primeras llamadas', 'Seguimiento']:
            del_grupo = suyos[suyos['grupo'] == grupo]
            if len(del_grupo):
                filas = '\n'.join(fila_html(p) for _, p in del_grupo.iterrows())
                bloques += f"<h3>{grupo} ({len(del_grupo)})</h3>\n<ol>{filas}</ol>\n"
        secciones.append(f"""<section id="{ancla}">
<h2>{escape(asesor)}</h2>
<p class="cuenta">{len(suyos)} personas para hoy, de {pendientes} pendientes. Empieza por las primeras llamadas.</p>
{bloques}</section>""")

    reglas = ''.join(f"<tr><td>{escape(r)}</td><td>+{pts}</td></tr>" for r, pts in PUNTOS.items())
    reglas += ''.join(f"<tr><td>Llegó por {escape(c)}</td><td>+{pts}</td></tr>"
                      for c, pts in PUNTOS_CANAL.items())

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A quién llamar hoy, {fecha}</title>
<style>{ESTILO}</style></head>
<body><main>
<p class="fecha">A quién llamar hoy, {fecha}</p>
<h1>{titulo}</h1>
<p class="resumen">{resumen}</p>
<nav aria-label="Ir a un asesor">{''.join(enlaces)}</nav>
{''.join(secciones)}
<footer>
<p><strong>Cómo se arma esta lista.</strong> Cada asesor recibe dos listas: primeras llamadas,
para quien nadie ha llamado, y seguimiento, para quien ya mostró interés o no contestó.
Dentro de cada una va primero quien suma más puntos. Si empatan, en primeras llamadas va quien
lleva más tiempo esperando, y en seguimiento, la llamada más reciente.</p>
<table>{reglas}</table>
<p>La lista no sabe cuántas veces se le ha marcado a alguien, solo el resultado del primer contacto.</p>
</footer>
</main></body></html>"""
    (CARPETA / archivo).write_text(html, encoding='utf-8')


## Programa principal

if __name__ == '__main__':
    hoy = pd.Timestamp(sys.argv[1]) if len(sys.argv) > 1 else HOY

    personas = cargar_personas(hoy)
    cola = armar_cola(personas)
    lista = elegir_del_dia(cola)

    # Comprobaciones. Si algo de esto falla, la lista no se debe usar.
    assert lista['persona'].is_unique, 'hay una persona repetida'
    assert lista['resultado'].isin(ABIERTOS).all(), 'hay alguien que ya compró o no le interesa'
    assert lista.groupby('asesor').size().max() <= CUPO_PRIMERAS + CUPO_SEGUIMIENTO, \
        'un asesor tiene más personas que sus cupos'
    assert set(cola['asesor']) <= set(ASESORES), 'hay un asesor que no está en ASESORES'

    escribir_html(lista, cola, hoy)
    print(f"Mañana del {hoy:%d/%m/%Y %H:%M}")
    print(f"Personas: {len(personas):,} · pendientes: {len(cola):,} · en la lista: {len(lista)}")
    print(f"Primeras llamadas: {(lista['grupo'] == 'Primeras llamadas').sum()} · "
          f"seguimiento: {(lista['grupo'] == 'Seguimiento').sum()}")
    print(f"Sin ninguna llamada: {(cola['resultado'] == 'sin_contactar').sum()}")
    print('Listo: lista_hoy.html')
