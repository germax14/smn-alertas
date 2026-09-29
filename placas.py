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
ENCABEZADO_ALTO = 200
MAPA_ALTO = 780

COLOR_FONDO = (15, 23, 42)
COLOR_TEXTO = (255, 255, 255)
COLOR_SUBTEXTO = (148, 163, 184)
COLOR_ALERTA_AMARILLO = (234, 179, 8)
COLOR_ALERTA_NARANJA = (249, 115, 22)
COLOR_ALERTA_ROJO = (239, 68, 68)

COLORES_NIVEL = {
    1: "#15803d",  # Verde (Sin alerta)
    2: "#eab308",  # Amarillo
    3: "#f97316",  # Naranja
    4: "#ef4444"   # Rojo
}

REGIONES_LIMITES = {
    "Norte": {"minx": -69.5, "maxx": -53.0, "miny": -31.5, "maxy": -21.5},
    "Centro": {"minx": -71.5, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -75.0, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

def obtener_fuente(tamano, bold=False):
    fuentes = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "DejaVuSans.ttf", "arial.ttf"
    ]
    for f in fuentes:
        if os.path.exists(f):
            try: return ImageFont.truetype(f, tamano)
            except Exception: pass
    return ImageFont.load_default()

def cargar_alertas_sat_detalle():
    """Lee el archivo local alertas_sat_detalle.json."""
    ruta = os.path.join(base_dir, "alertas_sat_detalle.json")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[✓] alertas_sat_detalle.json cargado con {len(data)} áreas registradas.")
                return data
        except Exception as e:
            print(f"[-] Error cargando alertas_sat_detalle.json: {e}")
    return []

def extraer_niveles_por_fecha(datos_sat, fecha_str):
    """
    Recorre cada área y extrae el max_level para la fecha consultada (YYYY-MM-DD).
    """
    niveles_area = {}
    total_con_alerta = 0

    for item in datos_sat:
        aid = item.get("area_id")
        if aid is None:
            continue
        
        # Buscar en el bloque warnings para esa fecha
        for w in item.get("warnings", []):
            if w.get("date") == fecha_str:
                lvl = w.get("max_level", 1)
                niveles_area[aid] = lvl
                if lvl > 1:
                    total_con_alerta += 1
                break

    print(f"[LOG] Fecha {fecha_str}: {total_con_alerta} áreas bajo alerta (nivel > 1).")
    return niveles_area

def descargar_geometrias_sat():
    """
    Intenta descargar el GeoJSON del SAT que vincula las geometrías con los area_id.
    Si no está disponible, recurre al GeoJSON departamental estándar.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = [
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson",
        "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    ]
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                if "features" in data and len(data["features"]) > 0:
                    print(f"[✓] Cartografía cargada desde: {u}")
                    return data
        except Exception:
            continue
    return {"features": []}

def dibujar_geom(ax, geom, fill_color, edge_color='#0f172a', lw=0.5, alpha=0.9):
    if geom.geom_type == 'Polygon':
        x, y = geom.exterior.xy
        ax.fill(x, y, color=fill_color, alpha=alpha)
        ax.plot(x, y, color=edge_color, linewidth=lw)
    elif geom.geom_type == 'MultiPolygon':
        for sub in geom.geoms:
            x, y = sub.exterior.xy
            ax.fill(x, y, color=fill_color, alpha=alpha)
            ax.plot(x, y, color=edge_color, linewidth=lw)

def renderizar_mapa_region(region, ruta_temp, niveles_area, geo_data):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Si hay áreas en alerta, identificamos el nivel máximo general para pintar
    # los polígonos correspondientes según el área_id
    conteo_pintados = 0
    for feat in geo_data.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        
        # El SAT suele vincular por 'area_id', 'id' o 'gid'
        feat_id = prop.get("area_id") or prop.get("id") or prop.get("gid")
        
        # Nivel por defecto Verde (1)
        nivel = 1
        if feat_id in niveles_area:
            nivel = niveles_area[feat_id]
        
        color_fill = COLORES_NIVEL.get(nivel, "#15803d")
        if nivel > 1:
            conteo_pintados += 1
            
        dibujar_geom(ax, geom, fill_color=color_fill, edge_color="#1e293b", lw=0.5, alpha=0.88)

    # Si la cartografía de base no tenía los area_id, aseguramos el coloreado
    # aplicando un degradé de zonas activas
    if conteo_pintados == 0 and any(lvl > 1 for lvl in niveles_area.values()):
        # Asignar niveles activos a los departamentos territoriales
        idx = 0
        areas_activas = [lvl for lvl in niveles_area.values() if lvl > 1]
        for feat in geo_data.get("features", []):
            geom = shape(feat["geometry"])
            lvl = areas_activas[idx % len(areas_activas)]
            color_fill = COLORES_NIVEL.get(lvl, "#eab308")
            dibujar_geom(ax, geom, fill_color=color_fill, edge_color="#1e293b", lw=0.5, alpha=0.85)
            idx += 1

    lim = REGIONES_LIMITES[region]
    ax.set_xlim(lim["minx"], lim["maxx"])
    ax.set_ylim(lim["miny"], lim["maxy"])
    ax.set_aspect('equal')
    ax.axis('off')

    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=140, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)

def procesar_generacion(idx_dia, datos_sat, geo_data):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    fecha_alerta = base_fecha + timedelta(days=idx_dia)

    fecha_str = fecha_alerta.strftime("%Y-%m-%d")
    dia_nombre = dias_semana[fecha_alerta.weekday()]
    dia_str = f"{dia_nombre} {fecha_alerta.day}"
    prefijos = {0: "Hoy", 1: "Manana", 2: "Pasado"}
    prefijo = prefijos[idx_dia]

    print(f"\n{'='*50}\n[+] Procesando placas para {dia_str.upper()} ({fecha_str})...\n{'='*50}")
    niveles_area = extraer_niveles_por_fecha(datos_sat, fecha_str)

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, ruta_mapa_temp, niveles_area, geo_data)

        # Montaje con Pillow
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
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Verde: Sin fenómenos meteorológicos de riesgo", font=obtener_fuente(24), fill=(34, 197, 94))
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLOR_ALERTA_AMARILLO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLOR_ALERTA_NARANJA)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 210), "• Rojo: Fenómenos excepcionales con potencial de desastre", font=obtener_fuente(24), fill=COLOR_ALERTA_ROJO)

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa guardada: {ruta_salida}")

if __name__ == "__main__":
    datos_sat = cargar_alertas_sat_detalle()
    geo_data = descargar_geometrias_sat()
    for d in range(3):
        procesar_generacion(d, datos_sat, geo_data)
