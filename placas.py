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

# Encuadres geográficos de recorte por región
REGIONES_LIMITES = {
    "Norte": {"minx": -69.0, "maxx": -53.0, "miny": -31.0, "maxy": -21.5},
    "Centro": {"minx": -71.0, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -74.5, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

COLORES_SAT = {
    "verde": "#15803d",
    "amarillo": "#eab308",
    "naranja": "#f97316",
    "rojo": "#ef4444"
}

PESO_SEVERIDAD = {
    "rojo": 4,
    "red": 4,
    "naranja": 3,
    "orange": 3,
    "amarillo": 2,
    "yellow": 2,
    "verde": 1,
    "green": 1
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

def descargar_poligonos_sat_smn():
    """Consulta los endpoints de GeoJSON con polígonos de alerta directa del SMN."""
    urls = [
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.json",
        "https://ssl.smn.gob.ar/ws/alertas/alertas_hoy.json"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=12)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                if isinstance(data, dict) and "features" in data and len(data["features"]) > 0:
                    print(f"[+] Polígonos SAT oficiales descargados desde: {u}")
                    return data
        except Exception:
            continue
    return None

def cargar_alertas_locales():
    """Lee y unifica los datos de los JSON locales en el repositorio."""
    archivos = ["alertas_sat_detalle.json", "alertas_por_provincia.json", "alertas_completas.json"]
    for arch in archivos:
        path = os.path.join(base_dir, arch)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    contenido = f.read().strip()
                    if contenido:
                        datos = json.loads(contenido)
                        print(f"[+] Datos de alertas locales cargados desde: {arch}")
                        return datos
            except Exception as e:
                print(f"[-] Error al leer {arch}: {e}")
    return []

def extraer_nivel_color(alerta_obj):
    color = alerta_obj.get("color") or alerta_obj.get("nivel") or alerta_obj.get("severidad") or ""
    color_norm = str(color).lower()
    for clave in PESO_SEVERIDAD:
        if clave in color_norm:
            if clave in ["red", "rojo"]: return "rojo"
            if clave in ["orange", "naranja"]: return "naranja"
            if clave in ["yellow", "amarillo"]: return "amarillo"
            if clave in ["green", "verde"]: return "verde"
    return "verde"

def obtener_color_por_nombre(depto_nombre, prov_nombre, datos_locales, dia_idx):
    depto_norm = normalizar_texto(depto_nombre)
    prov_norm = normalizar_texto(prov_nombre)

    lista = datos_locales if isinstance(datos_locales, list) else datos_locales.get("alertas", [])
    max_prio = 1
    color_ganador = "verde"

    for item in lista:
        item_dia = item.get("dia", 0)
        # Filtra si corresponde al día evaluado
        if item_dia == dia_idx or item_dia is None:
            zona_alerta = normalizar_texto(item.get("zona") or item.get("departamento") or item.get("nombre") or "")
            prov_alerta = normalizar_texto(item.get("provincia") or "")

            coincide = False
            if depto_norm and depto_norm in zona_alerta:
                coincide = True
            elif prov_norm and prov_norm in prov_alerta and (not zona_alerta or "toda" in zona_alerta):
                coincide = True

            if coincide:
                color = extraer_nivel_color(item)
                prio = PESO_SEVERIDAD.get(color, 1)
                if prio > max_prio:
                    max_prio = prio
                    color_ganador = color

    return COLORES_SAT.get(color_ganador, "#15803d")

def dibujar_geometria(ax, geom, color_relleno, color_borde='#0f172a', lw=0.6, alpha=0.9):
    if geom.geom_type == 'Polygon':
        x, y = geom.exterior.xy
        ax.fill(x, y, color=color_relleno, alpha=alpha)
        ax.plot(x, y, color=color_borde, linewidth=lw)
    elif geom.geom_type == 'MultiPolygon':
        for sub in geom.geoms:
            x, y = sub.exterior.xy
            ax.fill(x, y, color=color_relleno, alpha=alpha)
            ax.plot(x, y, color=color_borde, linewidth=lw)

def renderizar_mapa_region(region, dia_idx, ruta_temp, poligonos_sat, datos_locales):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Descarga la base geográfica oficial de departamentos
    url_base = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    r = requests.get(url_base, timeout=15)
    geojson_deptos = r.json() if r.status_code == 200 else {"features": []}

    # 1. Dibujar base territorial
    for feat in geojson_deptos.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        depto = prop.get("departamento", "")
        prov = prop.get("provincia", "")

        # Si no hay polígonos SAT directos, colorea directamente cada departamento cruzando con el JSON local
        if not poligonos_sat:
            color_depto = obtener_color_por_nombre(depto, prov, datos_locales, dia_idx)
            dibujar_geometria(ax, geom, color_relleno=color_depto, color_borde="#1e293b", lw=0.6, alpha=0.92)
        else:
            # Fondo territorial base en verde suave (sin alerta)
            dibujar_geometria(ax, geom, color_relleno="#15803d", color_borde="#1e293b", lw=0.6, alpha=0.5)

    # 2. Si hay polígonos vectoriales oficiales del SAT, los superpone
    if poligonos_sat:
        for feat in poligonos_sat.get("features", []):
            prop = feat.get("properties", {})
            dia_alerta = prop.get("dia", 0)
            if dia_alerta == dia_idx or dia_idx == 0:
                color_tipo = extraer_nivel_color(prop)
                color_hex = COLORES_SAT.get(color_tipo)
                if color_hex and color_hex != "#15803d":
                    try:
                        geom_al = shape(feat["geometry"])
                        dibujar_geometria(ax, geom_al, color_relleno=color_hex, color_borde="#ffffff", lw=1.0, alpha=0.88)
                    except Exception:
                        continue

    # Ajuste de coordenadas y encuadre
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
    poligonos_sat = descargar_poligonos_sat_smn()
    datos_locales = cargar_alertas_locales()

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, poligonos_sat, datos_locales)

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
