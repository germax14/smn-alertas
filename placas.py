import os
import sys
import json
import requests
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
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
    "Norte": {"minx": -68.0, "maxx": -53.0, "miny": -30.0, "maxy": -21.0},
    "Centro": {"minx": -70.0, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -75.0, "maxx": -62.0, "miny": -56.0, "maxy": -40.0}
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

def obtener_datos_alertas():
    # Intento de descarga en vivo
    url_alertas = "https://ssl.smn.gob.ar/ws/alertas/alertas.json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        resp = requests.get(url_alertas, headers=headers, timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            return resp.json()
    except Exception as e:
        print(f"[-] No se pudo consultar la API en vivo: {e}")

    # Fallback seguro a archivo local
    local_path = os.path.join(base_dir, "alertas_completas.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return json.loads(contenido)
        except Exception as e:
            print(f"[-] Archivo local no legible o corrupto: {e}")

    return {}

def renderizar_mapa_region(region, dia_idx, ruta_temp):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Dibuja la silueta geográfica base
    try:
        url_argentina = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
        gdf = gpd.read_file(url_argentina)
        arg = gdf[gdf['ISO_A3'] == 'ARG']
        arg.plot(ax=ax, color='#1e293b', edgecolor='#38bdf8', linewidth=1.2)
    except Exception:
        ax.plot([-70, -55], [-55, -20], color='#1e293b', alpha=0)

    # Encuadre de coordenadas por región
    lim = REGIONES_LIMITES[region]
    ax.set_xlim(lim["minx"], lim["maxx"])
    ax.set_ylim(lim["miny"], lim["maxy"])
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(ruta_temp, dpi=130, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)

def procesar_generacion(idx_dia):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    fecha_alerta = base_fecha + timedelta(days=idx_dia)

    dia_nombre = dias_semana[fecha_alerta.weekday()]
    dia_str = f"{dia_nombre} {fecha_alerta.day}"
    prefijos = {0: "Hoy", 1: "Manana", 2: "Pasado"}
    prefijo = prefijos[idx_dia]

    print(f"\n[+] Generando placas vectoriales para {dia_str.upper()}...")
    obtener_datos_alertas()

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp)

        # Montaje final de la placa con Pillow
        img = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        # Encabezado
        draw.text((50, 40), f"SISTEMA DE ALERTA TEMPRANA - {dia_str.upper()}", font=obtener_fuente(46, bold=True), fill=COLOR_TEXTO)
        draw.text((50, 110), f"Región: {region} | Servicio Meteorológico Nacional", font=obtener_fuente(28), fill=COLOR_SUBTEXTO)

        # Pegar mapa vectorial
        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((ANCHO_PLACA - 100, MAPA_ALTO), Image.Resampling.LANCZOS)
                img.paste(map_img, (50, ENCABEZADO_ALTO))
            os.remove(ruta_mapa_temp)

        # Pie de placa informativo
        draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=(30, 41, 59))
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLOR_ALERTA_AMARILLO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLOR_ALERTA_NARANJA)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Rojo: Fenómenos excepcionales con potencial de provocar desastres", font=obtener_fuente(24), fill=COLOR_ALERTA_ROJO)

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa generada: {ruta_salida}")

if __name__ == "__main__":
    for d in range(3):
        procesar_generacion(d)
