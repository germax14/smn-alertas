import os
import sys
import json
import requests
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape, Polygon, MultiPolygon
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
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

# Delimitaciones para zoom de encuadre por región
REGIONES_LIMITES = {
    "Norte": {"minx": -69.0, "maxx": -53.0, "miny": -31.0, "maxy": -21.5},
    "Centro": {"minx": -71.0, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -74.5, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

COLORES_NIVEL = {
    "verde": "#22c55e",
    "amarillo": "#eab308",
    "naranja": "#f97316",
    "rojo": "#ef4444",
    "normal": "#1e293b"
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

def leer_datos_alertas():
    # Intenta leer los archivos que ya están en el repositorio
    archivos = ["alertas_por_provincia.json", "alertas_sat_detalle.json", "alertas_completas.json"]
    for arch in archivos:
        ruta = os.path.join(base_dir, arch)
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
            except Exception:
                continue
    return {}

def obtener_color_alerta_zona(region, idx_dia, datos):
    # Por defecto, fondo territorial estándar
    return "#1e293b"

def dibujar_poligono(ax, poly, fill_color, edge_color='#38bdf8', lw=1.2):
    if poly.geom_type == 'Polygon':
        x, y = poly.exterior.xy
        ax.fill(x, y, color=fill_color, alpha=0.9)
        ax.plot(x, y, color=edge_color, linewidth=lw)
    elif poly.geom_type == 'MultiPolygon':
        for sub_p in poly.geoms:
            x, y = sub_p.exterior.xy
            ax.fill(x, y, color=fill_color, alpha=0.9)
            ax.plot(x, y, color=edge_color, linewidth=lw)

def renderizar_mapa_region(region, dia_idx, ruta_temp, datos_alertas):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Descarga GeoJSON de provincias de Argentina desde repositorio abierto IGN/Georef
    url_provincias = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    
    geo_dibujado = False
    try:
        r = requests.get(url_provincias, timeout=12)
        if r.status_code == 200:
            geojson_data = r.json()
            for feature in geojson_data.get("features", []):
                geom = shape(feature["geometry"])
                dibujar_poligono(ax, geom, fill_color="#1e293b", edge_color="#334155", lw=0.6)
            geo_dibujado = True
    except Exception as e:
        print(f"[-] No se pudo cargar provincias detalladas: {e}")

    if not geo_dibujado:
        # Fallback con contorno continental argentino simplificado si no hay red
        silueta_arg = Polygon([
            (-65.5, -22.0), (-62.0, -22.0), (-57.5, -25.5), (-53.5, -26.0),
            (-57.0, -30.0), (-58.0, -34.0), (-57.0, -36.0), (-62.0, -39.0),
            (-65.0, -43.0), (-66.0, -47.0), (-65.0, -50.0), (-68.0, -55.0),
            (-73.5, -52.0), (-72.0, -47.0), (-71.0, -41.0), (-70.0, -35.0),
            (-69.5, -31.0), (-68.5, -26.0), (-66.5, -23.0)
        ])
        dibujar_poligono(ax, silueta_arg, fill_color="#1e293b", edge_color="#38bdf8", lw=1.5)

    # Encuadre y vista regional
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

    print(f"\n[+] Renderizando placas para {dia_str.upper()}...")
    datos_alertas = leer_datos_alertas()

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, datos_alertas)

        # Montaje con Pillow
        img = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        # Encabezado
        draw.text((50, 40), f"SISTEMA DE ALERTA TEMPRANA - {dia_str.upper()}", font=obtener_fuente(46, bold=True), fill=COLOR_TEXTO)
        draw.text((50, 110), f"Región: {region} | Servicio Meteorológico Nacional", font=obtener_fuente(28), fill=COLOR_SUBTEXTO)

        # Inserción de mapa centrado
        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((ANCHO_PLACA - 100, MAPA_ALTO), Image.Resampling.LANCZOS)
                img.paste(map_img, (50, ENCABEZADO_ALTO))
            try:
                os.remove(ruta_mapa_temp)
            except Exception:
                pass

        # Pie informativo
        draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=(30, 41, 59))
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLOR_ALERTA_AMARILLO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLOR_ALERTA_NARANJA)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Rojo: Fenómenos excepcionales con potencial de provocar desastres", font=obtener_fuente(24), fill=COLOR_ALERTA_ROJO)

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa generada con éxito: {ruta_salida}")

if __name__ == "__main__":
    for d in range(3):
        procesar_generacion(d)
