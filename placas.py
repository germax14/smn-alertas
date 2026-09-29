import os
import sys
import json
import re
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

# Límites de encuadre geográfico (Longitud min/max, Latitud min/max)
REGIONES_LIMITES = {
    "Norte": {"minx": -69.5, "maxx": -53.0, "miny": -31.5, "maxy": -21.5},
    "Centro": {"minx": -71.5, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -75.0, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

COLORES_SAT = {
    "verde": "#15803d",
    "amarillo": "#eab308",
    "naranja": "#f97316",
    "rojo": "#ef4444"
}

PESO_SEVERIDAD = {
    "rojo": 4, "red": 4,
    "naranja": 3, "orange": 3,
    "amarillo": 2, "yellow": 2,
    "verde": 1, "green": 1
}

def normalizar_texto(texto):
    if not texto:
        return ""
    txt = str(texto).lower().strip()
    txt = re.sub(r'[áàäâ]', 'a', txt)
    txt = re.sub(r'[éèëê]', 'e', txt)
    txt = re.sub(r'[íìïî]', 'i', txt)
    txt = re.sub(r'[óòöô]', 'o', txt)
    txt = re.sub(r'[úùüû]', 'u', txt)
    txt = re.sub(r'[^a-z0-9 ]', ' ', txt)
    return ' '.join(txt.split())

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

def extraer_nivel_color(texto_o_dic):
    if isinstance(texto_o_dic, dict):
        val = texto_o_dic.get("color") or texto_o_dic.get("nivel") or texto_o_dic.get("severidad") or ""
    else:
        val = str(texto_o_dic)
    val_norm = str(val).lower()
    for k in ["rojo", "red"]:
        if k in val_norm: return "rojo"
    for k in ["naranja", "orange"]:
        if k in val_norm: return "naranja"
    for k in ["amarillo", "yellow"]:
        if k in val_norm: return "amarillo"
    return "verde"

def obtener_capas_alertas_smn(dia_idx):
    """
    Obtiene los GeoJSON de áreas de alerta que consume el visor web oficial del SMN.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.smn.gob.ar/alertas"
    }
    
    # Endpoints de capas geoespaciales del SMN
    sufijo_dia = f"_{dia_idx}" if dia_idx > 0 else ""
    urls = [
        f"https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos{sufijo_dia}.geojson",
        f"https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos{sufijo_dia}.json",
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson",
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.json"
    ]

    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=12)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                if isinstance(data, dict) and "features" in data and len(data["features"]) > 0:
                    print(f"[+] Capa de polígonos obtenida desde: {u}")
                    return data
        except Exception:
            continue

    # Respaldo en caso de tener JSON en el repo
    for arch in ["alertas_sat_detalle.json", "alertas_completas.json", "alertas_por_provincia.json"]:
        path = os.path.join(base_dir, arch)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    contenido = f.read().strip()
                    if contenido:
                        d = json.loads(contenido)
                        if isinstance(d, dict) and "features" in d and len(d["features"]) > 0:
                            return d
            except Exception:
                pass
    return None

def cargar_alertas_por_depto():
    """Fallback tabular en caso de que vengan solo listas de nombres."""
    for arch in ["alertas_por_provincia.json", "alertas_sat_detalle.json"]:
        path = os.path.join(base_dir, arch)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    c = f.read().strip()
                    if c:
                        return json.loads(c)
            except Exception:
                pass
    return []

def dibujar_geom(ax, geom, fill_color, edge_color='#0f172a', lw=0.6, alpha=0.9):
    if geom.geom_type == 'Polygon':
        x, y = geom.exterior.xy
        ax.fill(x, y, color=fill_color, alpha=alpha)
        ax.plot(x, y, color=edge_color, linewidth=lw)
    elif geom.geom_type == 'MultiPolygon':
        for sub in geom.geoms:
            x, y = sub.exterior.xy
            ax.fill(x, y, color=fill_color, alpha=alpha)
            ax.plot(x, y, color=edge_color, linewidth=lw)

def renderizar_mapa_region(region, dia_idx, ruta_temp, poligonos_alerta, datos_deptos):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Descargar límites departamentales de Argentina
    url_deptos = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url_deptos, timeout=15)
        deptos_geojson = r.json() if r.status_code == 200 else {"features": []}
    except Exception:
        deptos_geojson = {"features": []}

    # 1. Dibujar el mapa base de departamentos
    for feat in deptos_geojson.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        depto_nom = normalizar_texto(prop.get("departamento", ""))
        prov_nom = normalizar_texto(prop.get("provincia", ""))

        color_base = "#14532d"  # Verde normalidad

        # Si no hubo polígonos directos, evaluar por coincidencia de texto
        if not poligonos_alerta and datos_deptos:
            lista_alertas = datos_deptos if isinstance(datos_deptos, list) else datos_deptos.get("alertas", [])
            max_prio = 1
            for item in lista_alertas:
                z = normalizar_texto(item.get("zona") or item.get("departamento") or "")
                p = normalizar_texto(item.get("provincia") or "")
                d_item = item.get("dia", 0)
                if (d_item == dia_idx or d_item is None) and ((depto_nom and depto_nom in z) or (prov_nom and prov_nom in p and ("toda" in z or not z))):
                    c = extraer_nivel_color(item)
                    pr = PESO_SEVERIDAD.get(c, 1)
                    if pr > max_prio:
                        max_prio = pr
                        color_base = COLORES_SAT.get(c, "#14532d")

        dibujar_geom(ax, geom, fill_color=color_base, edge_color="#1e293b", lw=0.5, alpha=0.8)

    # 2. Superponer polígonos de alerta oficiales del SMN
    if poligonos_alerta:
        for feat in poligonos_alerta.get("features", []):
            prop = feat.get("properties", {})
            d_alerta = prop.get("dia", dia_idx)
            if d_alerta == dia_idx or dia_idx == 0:
                color_tipo = extraer_nivel_color(prop)
                color_hex = COLORES_SAT.get(color_tipo)
                if color_hex and color_hex != "#15803d":
                    try:
                        g_alerta = shape(feat["geometry"])
                        dibujar_geom(ax, g_alerta, fill_color=color_hex, edge_color="#ffffff", lw=1.0, alpha=0.88)
                    except Exception:
                        continue

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

    print(f"\n[+] Procesando placas para {dia_str.upper()}...")
    poligonos_alerta = obtener_capas_alertas_smn(idx_dia)
    datos_deptos = cargar_alertas_por_depto() if not poligonos_alerta else None

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, poligonos_alerta, datos_deptos)

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
    for d in range(3):
        procesar_generacion(d)
