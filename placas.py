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

COLORES_NIVEL = {
    1: "#14532d",  # Verde oscuro (Base normalidad)
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
    """Lee las áreas y niveles activos desde el archivo local generado previamente."""
    ruta = os.path.join(base_dir, "alertas_sat_detalle.json")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data = data.get("data", list(data.values())[0] if data else [])
                print(f"[✓] Datos locales leídos: {len(data)} áreas con historial.")
                return data
        except Exception as e:
            print(f"[-] Error cargando JSON de alertas: {e}")
    return []

def extraer_niveles_por_fecha(datos_sat, fecha_str):
    """Obtiene un diccionario {area_id: max_level} para la fecha dada."""
    niveles = {}
    for item in datos_sat:
        aid = str(item.get("area_id", ""))
        if not aid: continue
        for w in item.get("warnings", []):
            if w.get("date") == fecha_str:
                niveles[aid] = w.get("max_level", 1)
                break
    activas = sum(1 for lvl in niveles.values() if lvl > 1)
    print(f"[LOG] Para {fecha_str} hay {activas} áreas bajo alerta activa.")
    return niveles

def descargar_base_ign():
    """Capa 1: Garantiza que el mapa de Argentina siempre se dibuje (100% confiable)."""
    url = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            print("[✓] Capa base territorial (IGN) obtenida con éxito.")
            return r.json()
    except Exception as e:
        print(f"[-] Error crítico de red al descargar mapa base: {e}")
    return {"features": []}

def descargar_poligonos_smn():
    """Capa 2: Intenta descargar los polígonos exactos del SMN a través de un proxy."""
    url_smn = "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson"
    urls = [
        f"https://api.allorigins.win/raw?url={url_smn}",
        url_smn
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=15)
            if r.status_code == 200:
                try:
                    data = r.json()
                    if "features" in data:
                        print(f"[✓] Capa vectorial de alertas SMN descargada correctamente.")
                        return data
                except Exception:
                    pass
        except Exception:
            continue
    print("[-] No se pudieron descargar los polígonos vectoriales del SMN.")
    return None

def dibujar_geom(ax, geom, fill_color, edge_color='#0f172a', lw=0.4, alpha=0.9):
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

    # 1. Dibujar siempre la Capa Base territorial (Fondo Verde)
    for feat in base_ign.get("features", []):
        g = feat.get("geometry")
        if g:
            dibujar_geom(ax, shape(g), fill_color="#14532d", edge_color="#1e293b", lw=0.4, alpha=0.7)

    # 2. Superponer la Capa de Alertas del SMN si la descarga funcionó
    pintados = 0
    if poligonos_smn:
        for feat in poligonos_smn.get("features", []):
            prop = feat.get("properties", {})
            aid = str(prop.get("ARE_IN_ID") or prop.get("are_in_id") or prop.get("area_id") or "")
            nivel = niveles_area.get(aid, 1)
            
            # Solo dibuja por encima si hay una alerta activa (Amarillo/Naranja/Rojo)
            if nivel > 1:
                g = feat.get("geometry")
                if g:
                    color_fill = COLORES_NIVEL.get(nivel, "#15803d")
                    dibujar_geom(ax, shape(g), fill_color=color_fill, edge_color="#ffffff", lw=0.8, alpha=0.95)
                    pintados += 1

    print(f"[LOG] Región {region}: {pintados} polígonos de alerta coloreados por encima de la base.")

    lim = REGIONES_LIMITES[region]
    ax.set_xlim(lim["minx"], lim["maxx"])
    ax.set_ylim(lim["miny"], lim["maxy"])
    ax.set_aspect('equal')
    ax.axis('off')

    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=140, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)

def procesar_generacion(idx_dia, datos_sat, base_ign, poligonos_smn):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    fecha_alerta = base_fecha + timedelta(days=idx_dia)

    fecha_str = fecha_alerta.strftime("%Y-%m-%d")
    dia_nombre = dias_semana[fecha_alerta.weekday()]
    dia_str = f"{dia_nombre} {fecha_alerta.day}"
    prefijos = {0: "Hoy", 1: "Manana", 2: "Pasado"}
    prefijo = prefijos[idx_dia]

    print(f"\n{'='*50}\n[+] Generando placas para {dia_str.upper()} ({fecha_str})\n{'='*50}")
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
            try:
                os.remove(ruta_mapa_temp)
            except Exception:
                pass

        draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=(30, 41, 59))
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Verde: Sin fenómenos meteorológicos de riesgo", font=obtener_fuente(24), fill="#22c55e")
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Amarillo: Posibles fenómenos con capacidad de daño", font=obtener_fuente(24), fill=COLORES_NIVEL[2])
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=obtener_fuente(24), fill=COLORES_NIVEL[3])
        draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 210), "• Rojo: Fenómenos excepcionales con potencial de desastre", font=obtener_fuente(24), fill=COLORES_NIVEL[4])

        img.save(ruta_salida, format="PNG")
        print(f"[✓] Placa guardada: {ruta_salida}")

if __name__ == "__main__":
    datos_sat = cargar_alertas_sat_detalle()
    base_ign = descargar_base_ign()
    poligonos_smn = descargar_poligonos_smn()
    
    for d in range(3):
        procesar_generacion(d, datos_sat, base_ign, poligonos_smn)
