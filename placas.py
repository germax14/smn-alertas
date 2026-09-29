import os
import sys
import json
import requests
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape
from PIL import Image, ImageDraw, ImageFont

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CARPETA_SALIDA = os.path.join(base_dir, "placas_mapa")
os.makedirs(CARPETA_SALIDA, exist_ok=True)

ANCHO_PLACA = 1080
ALTO_PLACA = 1350

COLOR_FONDO = (15, 23, 42)
COLOR_TEXTO = (255, 255, 255)
COLOR_SUBTEXTO = (148, 163, 184)
COLOR_ALERTA_AMARILLO = (234, 179, 8)
COLOR_ALERTA_NARANJA = (249, 115, 22)
COLOR_ALERTA_ROJO = (239, 68, 68)

ENCABEZADO_ALTO = 200
MAPA_ALTO = 780

REGIONES_LIMITES = {
    "Norte": {"minx": -69.0, "maxx": -53.0, "miny": -31.0, "maxy": -21.5},
    "Centro": {"minx": -71.0, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -74.5, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

COLORES_ALERTA = {
    "verde": "#15803d",
    "amarillo": "#eab308",
    "naranja": "#f97316",
    "rojo": "#ef4444",
    "base": "#1e293b"
}

def obtener_fuente(tamano, bold=False):
    fuentes_posibles = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "DejaVuSans.ttf",
        "arial.ttf"
    ]
    for ruta in fuentes_posibles:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                continue
    return ImageFont.load_default()

def cargar_alertas():
    # Lee los datos procesados en el repositorio
    for archivo in ["alertas_sat_detalle.json", "alertas_por_provincia.json", "alertas_completas.json"]:
        ruta = os.path.join(base_dir, archivo)
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    contenido = f.read().strip()
                    if contenido:
                        return json.loads(contenido)
            except Exception:
                continue
    return {}

def obtener_color_departamento(nombre_depto, prov_nombre, datos_alertas, idx_dia):
    if not datos_alertas:
        return COLORES_ALERTA["base"]

    nombre_normalizado = (nombre_depto or "").strip().lower()
    prov_normalizada = (prov_nombre or "").strip().lower()

    # Si hay estructura de alertas detalladas por zona
    alertas_lista = datos_alertas if isinstance(datos_alertas, list) else datos_alertas.get("alertas", [])
    
    nivel_prioridad = {"rojo": 4, "naranja": 3, "amarillo": 2, "verde": 1}
    color_max = "base"
    prio_max = 0

    for al in alertas_lista:
        zona = str(al.get("zona", "")).lower()
        prov = str(al.get("provincia", "")).lower()
        color = str(al.get("color", "")).lower()
        dia_alerta = al.get("dia", 0)

        # Si coincide el día (o no especifica) y la zona/provincia
        if (dia_alerta == idx_dia or "dia" not in al) and (nombre_normalizado in zona or prov_normalizada in prov):
            prio = nivel_prioridad.get(color, 0)
            if prio > prio_max:
                prio_max = prio
                color_max = color

    return COLORES_ALERTA.get(color_max, COLORES_ALERTA["base"])

def dibujar_poligono(ax, poly, fill_color, edge_color='#334155', lw=0.6):
    if poly.geom_type == 'Polygon':
        x, y = poly.exterior.xy
        ax.fill(x, y, color=fill_color, alpha=0.92)
        ax.plot(x, y, color=edge_color, linewidth=lw)
    elif poly.geom_type == 'MultiPolygon':
        for sub_p in poly.geoms:
            x, y = sub_p.exterior.xy
            ax.fill(x, y, color=fill_color, alpha=0.92)
            ax.plot(x, y, color=edge_color, linewidth=lw)

def renderizar_mapa_region(region, dia_idx, ruta_temp, datos_alertas):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    url_provincias = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url_provincias, timeout=15)
        if r.status_code == 200:
            geojson_data = r.json()
            for feature in geojson_data.get("features", []):
                geom = shape(feature["geometry"])
                prop = feature.get("properties", {})
                depto = prop.get("departamento", "")
                prov = prop.get("provincia", "")

                color_relleno = obtener_color_departamento(depto, prov, datos_alertas, dia_idx)
                dibujar_poligono(ax, geom, fill_color=color_relleno, edge_color="#475569", lw=0.7)
    except Exception as e:
        print(f"[-] Error renderizando departamentos: {e}")

    lim = REGIONES_LIMITES[region]
    ax.set_xlim(lim["minx"], lim["maxx"])
    ax.set_ylim(lim["miny"], lim["maxy"])
    ax.set_aspect('equal')
    ax.axis('off')

    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=140, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)

def procesar_generacion(idx_dia):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    fecha_alerta = base_fecha + timedelta(days=idx_dia)

    dia_nombre = dias_semana[fecha_alerta.weekday()]
    dia_str = f"{dia_nombre} {fecha_alerta.day}"
    prefijos = {0: "Hoy", 1: "Manana", 2: "Pasado"}
    prefijo = prefijos[idx_dia]

    print(f"\n[+] Coloreando placas vectoriales para {dia_str.upper()}...")
    datos_alertas = cargar_alertas()

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, datos_alertas)

        img = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        draw.text((50, 40), f"SISTEMA DE ALERTA TEMPRANA - {dia_str.upper()}", font=obtener_fuente(46, bold=True), fill=COLOR_TEXTO)
        draw.text((50, 110), f"Región: {region} | Servicio Meteorológico Nacional", font=obtener_fuente(28), fill=COLOR_SUBTEXTO)

        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((ANCHO_PLACA - 100, MAPA_ALTO), Image.Resampling.LANCZOS)
                img.paste(map_img, (50, ENCABEZADO_ALTO))
            try:
                os.remove(ruta_mapa_temp)
            except Exception:
                pass

        draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=(30, 41, 59))
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLOR_ALERTA_AMARILLO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLOR_ALERTA_NARANJA)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Rojo: Fenómenos excepcionales con potencial de provocar desastres", font=obtener_fuente(24), fill=COLOR_ALERTA_ROJO)

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa guardada: {ruta_salida}")

if __name__ == "__main__":
    for d in range(3):
        procesar_generacion(d)
