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
import contextily as ctx
from shapely import wkt
import geopandas as gpd

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

COLOR_FONDO = (10, 15, 30)
COLOR_TEXTO = (255, 255, 255)
COLOR_SUBTEXTO = (148, 163, 184)
COLOR_CAJA_GRIS = (20, 25, 45)
COLOR_AMARILLO = (255, 204, 0)
COLOR_ROJO = (220, 38, 38)
COLOR_BORDE = (30, 41, 59)

COLORES_NIVEL = {
    1: "#14532d",  # Verde oscuro
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

def dibujar_caja_redondeada(draw, xy, fill, outline=None, width=0, radius=10):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

# ==========================================
# PARTE 1: AVISOS A CORTO PLAZO (SATEM)
# ==========================================

def descargar_acp_smn():
    url = "https://ws.smn.gob.ar/alerts/type/AC"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"[✓] ACP: {len(data)} Avisos a Corto Plazo obtenidos.")
                return data
    except Exception as e:
        print(f"[-] Error descargando ACP: {e}")
    return []

def generar_mapa_acp(poligono_wkt, ruta_temp):
    fig, ax = plt.subplots(figsize=(6, 6))
    try:
        geom = wkt.loads(poligono_wkt)
        gdf = gpd.GeoDataFrame(index=[0], crs='epsg:4326', geometry=[geom])
        gdf = gdf.to_crs(epsg=3857)
        gdf.plot(ax=ax, facecolor='red', edgecolor='red', alpha=0.3, linewidth=2)
        for x, y in list(geom.exterior.coords):
            ax.plot(x, y, marker='o', color='yellow', markeredgecolor='black', markersize=6, transform=ctx.crs.WGS84_to_Mercator)
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception as e:
        print(f"[-] Error renderizando mapa ACP: {e}")
        ax.set_facecolor('#d1d5db')
    ax.set_axis_off()
    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=150, bbox_inches='tight', pad_inches=0)
    plt.close(fig)

def crear_placa_acp(acp_data, idx):
    hora_emision = acp_data.get("updateTime", "")[-8:-3] or "12:00"
    try:
        hora_validez = (datetime.strptime(hora_emision, "%H:%M") + timedelta(hours=3)).strftime("%H:%M")
    except:
        hora_validez = "15:00"

    titulo_fenomeno = acp_data.get("title", "TORMENTAS FUERTES CON LLUVIAS INTENSAS.").upper()
    
    zonas_dict = acp_data.get("zones", {})
    provincias = {}
    for cod, desc in zonas_dict.items():
        if " - " in desc:
            prov, depto = desc.split(" - ", 1)
        else:
            prov, depto = "ZONA", desc
        if prov not in provincias: provincias[prov] = []
        provincias[prov].append(depto)

    img = Image.new("RGB", (ANCHO_PLACA, 1080), COLOR_FONDO)
    draw = ImageDraw.Draw(img)

    draw.ellipse([(40, 30), (120, 110)], fill=(255, 255, 255))
    draw.text((150, 40), "SATEM ARGENTINA", font=obtener_fuente(40, bold=True), fill=COLOR_TEXTO)
    draw.text((150, 85), "Soporte y Alerta Temprana ante Eventos Meteorológicos", font=obtener_fuente(20), fill=(56, 189, 248))

    draw.text((40, 140), "AVISO A CORTO PLAZO", font=obtener_fuente(35, bold=True), fill=COLOR_AMARILLO)

    dibujar_caja_redondeada(draw, [(40, 190), (250, 280)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((75, 205), "HORA DE EMISIÓN", font=obtener_fuente(14), fill=COLOR_SUBTEXTO)
    draw.text((65, 235), f"{hora_emision} HS", font=obtener_fuente(28, bold=True), fill=COLOR_TEXTO)

    dibujar_caja_redondeada(draw, [(270, 190), (480, 280)], fill=COLOR_CAJA_GRIS, outline=COLOR_AMARILLO, width=2)
    draw.text((310, 205), "VÁLIDO HASTA", font=obtener_fuente(14), fill=COLOR_AMARILLO)
    draw.text((300, 235), f"{hora_validez} HS", font=obtener_fuente(28, bold=True), fill=COLOR_AMARILLO)

    dibujar_caja_redondeada(draw, [(40, 310), (480, 520)], fill=(40, 15, 20), outline=COLOR_ROJO, width=2)
    draw.text((60, 330), "FENÓMENO PREVISTO", font=obtener_fuente(14, bold=True), fill=COLOR_ROJO)
    
    import textwrap
    lines = textwrap.wrap(titulo_fenomeno, width=25)
    y_text = 370
    for line in lines:
        draw.text((60, y_text), line, font=obtener_fuente(24, bold=True), fill=COLOR_TEXTO)
        y_text += 35

    dibujar_caja_redondeada(draw, [(40, 540), (480, 850)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((60, 560), "ZONAS BAJO ALERTA", font=obtener_fuente(14, bold=True), fill=(56, 189, 248))
    
    y_zona = 600
    for prov, deptos in provincias.items():
        draw.text((60, y_zona), f"{prov}:", font=obtener_fuente(24, bold=True), fill=COLOR_AMARILLO)
        y_zona += 35
        depto_str = " • ".join(deptos) + "."
        lines_d = textwrap.wrap(depto_str, width=32)
        for ld in lines_d:
            draw.text((60, y_zona), ld, font=obtener_fuente(20, bold=True), fill=COLOR_TEXTO)
            y_zona += 28
        y_zona += 10

    dibujar_caja_redondeada(draw, [(40, 870), (1040, 980)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((60, 890), "MEDIDAS DE PREVENCIÓN INMEDIATA", font=obtener_fuente(14, bold=True), fill=(56, 189, 248))
    draw.text((60, 920), "• Permanezca en construcciones cerradas y asegure objetos que puedan volarse.", font=obtener_fuente(16), fill=COLOR_SUBTEXTO)
    draw.text((60, 945), "• No circule por calles anegadas y manténgase alejado de postes y árboles.", font=obtener_fuente(16), fill=COLOR_SUBTEXTO)

    ruta_mapa_temp = os.path.join(base_dir, f"temp_mapa_{idx}.png")
    wkt_poly = acp_data.get("polygon", "")
    if wkt_poly:
        generar_mapa_acp(wkt_poly, ruta_mapa_temp)
        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((530, 660), Image.Resampling.LANCZOS)
                draw.rectangle([(508, 188), (1042, 852)], outline=COLOR_ROJO, width=2)
                img.paste(map_img, (510, 190))
            os.remove(ruta_mapa_temp)

    draw.text((40, 1020), "Datos oficiales: Servicio Meteorológico Nacional (SMN)", font=obtener_fuente(12), fill=(75, 85, 99))
    ruta_salida = os.path.join(CARPETA_SALIDA, f"ACP_{idx}.png")
    img.save(ruta_salida, format="PNG")
    print(f"[✓] Placa ACP guardada: {ruta_salida}")

# ==========================================
# PARTE 2: ALERTAS REGIONALES (HOY/MAÑANA)
# ==========================================

def cargar_alertas_sat_detalle():
    ruta = os.path.join(base_dir, "alertas_sat_detalle.json")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict): data = data.get("data", list(data.values())[0] if data else [])
                print(f"[✓] Regional: alertas_sat_detalle.json cargado ({len(data)} áreas).")
                return data
        except Exception as e: print(f"[-] Error cargando alertas: {e}")
    return []

def extraer_niveles_por_fecha(datos_sat, fecha_str):
    niveles = {}
    for item in datos_sat:
        aid = str(item.get("area_id", ""))
        if not aid: continue
        for w in item.get("warnings", []):
            if w.get("date") == fecha_str:
                niveles[aid] = w.get("max_level", 1)
                break
    return niveles

def descargar_base_ign():
    url = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return {"features": []}

def descargar_poligonos_smn():
    url_smn = "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson"
    try:
        r = requests.get(f"https://api.allorigins.win/raw?url={url_smn}", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if "features" in d: return d
    except Exception: pass
    return None

def dibujar_geom_simple(ax, geom, fill_color, edge_color='#0f172a', lw=0.4, alpha=0.9):
    if geom.geom_type == 'Polygon':
        x, y = geom.exterior.xy
        ax.fill(x, y, color=fill_color, alpha=alpha)
        ax.plot(x, y, color=edge_color, linewidth=lw)
    elif geom.geom_type == 'MultiPolygon':
        for sub in geom.geoms:
            x, y = sub.exterior.xy
            ax.fill(x, y, color=fill_color, alpha=alpha)
            ax.plot(x, y, color=edge_color, linewidth=lw)

def renderizar_mapa_region(region, ruta_temp, niveles_area, base_ign, poligonos_smn):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    for feat in base_ign.get("features", []):
        g = feat.get("geometry")
        if g: dibujar_geom_simple(ax, shape(g), fill_color="#14532d", edge_color="#1e293b", lw=0.4, alpha=0.7)

    if poligonos_smn:
        for feat in poligonos_smn.get("features", []):
            prop = feat.get("properties", {})
            aid = str(prop.get("ARE_IN_ID") or prop.get("are_in_id") or prop.get("area_id") or "")
            nivel = niveles_area.get(aid, 1)
            if nivel > 1:
                g = feat.get("geometry")
                if g: dibujar_geom_simple(ax, shape(g), fill_color=COLORES_NIVEL.get(nivel), edge_color="#ffffff", lw=0.8, alpha=0.95)

    lim = REGIONES_LIMITES[region]
    ax.set_xlim(lim["minx"], lim["maxx"])
    ax.set_ylim(lim["miny"], lim["maxy"])
    ax.set_aspect('equal')
    ax.axis('off')
    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=140, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)

def procesar_generacion_regional(idx_dia, datos_sat, base_ign, poligonos_smn):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    fecha_alerta = base_fecha + timedelta(days=idx_dia)
    fecha_str = fecha_alerta.strftime("%Y-%m-%d")
    dia_str = f"{dias_semana[fecha_alerta.weekday()]} {fecha_alerta.day}"
    prefijo = {0: "Hoy", 1: "Manana", 2: "Pasado"}[idx_dia]

    niveles_area = extraer_niveles_por_fecha(datos_sat, fecha_str)

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, ruta_mapa_temp, niveles_area, base_ign, poligonos_smn)

        img = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        draw.text((50, 40), f"SISTEMA DE ALERTA TEMPRANA - {dia_str.upper()}", font=obtener_fuente(46, bold=True), fill=COLOR_TEXTO)
        draw.text((50, 110), f"Región: {region} | Servicio Meteorológico Nacional", font=obtener_fuente(28), fill=COLOR_SUBTEXTO)

        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((ANCHO_PLACA - 100, MAPA_ALTO), Image.Resampling.LANCZOS)
                img.paste(map_img, (50, ENCABEZADO_ALTO))
            os.remove(ruta_mapa_temp)

        draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=COLOR_CAJA_GRIS)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Verde: Sin fenómenos meteorológicos de riesgo", font=obtener_fuente(24), fill="#22c55e")
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLORES_NIVEL[2])
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLORES_NIVEL[3])
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 210), "• Rojo: Fenómenos excepcionales con potencial de desastre", font=obtener_fuente(24), fill=COLORES_NIVEL[4])

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa regional guardada: {ruta_salida}")

if __name__ == "__main__":
    # 1. Generar placas de Aviso a Corto Plazo (ACP) si hay vigentes
    acps = descargar_acp_smn()
    if acps:
        for i, acp in enumerate(acps):
            crear_placa_acp(acp, i)
    else:
        print("[LOG] No hay Avisos a Corto Plazo (ACP) activos en este momento.")

    # 2. Generar placas Regionales de Alerta (Hoy, Mañana, Pasado)
    datos_sat = cargar_alertas_sat_detalle()
    base_ign = descargar_base_ign()
    poligonos_smn = descargar_poligonos_smn()
    
    for d in range(3):
        procesar_generacion_regional(d, datos_sat, base_ign, poligonos_smn)
