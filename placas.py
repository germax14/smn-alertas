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
ENCABEZADO_ALTO = 200
MAPA_ALTO = 780

COLOR_FONDO = (15, 23, 42)
COLOR_TEXTO = (255, 255, 255)
COLOR_SUBTEXTO = (148, 163, 184)
COLOR_ALERTA_AMARILLO = (234, 179, 8)
COLOR_ALERTA_NARANJA = (249, 115, 22)
COLOR_ALERTA_ROJO = (239, 68, 68)

COLORES_SAT = {
    "verde": "#15803d",
    "amarillo": "#eab308",
    "naranja": "#f97316",
    "rojo": "#ef4444"
}

PESO_SEVERIDAD = {
    "rojo": 4, "naranja": 3, "amarillo": 2, "verde": 1
}

REGIONES_LIMITES = {
    "Norte": {"minx": -69.5, "maxx": -53.0, "miny": -31.5, "maxy": -21.5},
    "Centro": {"minx": -71.5, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -75.0, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

def normalizar(txt):
    if not txt: return ""
    txt = str(txt).lower().strip()
    txt = re.sub(r'[áàäâ]', 'a', txt)
    txt = re.sub(r'[éèëê]', 'e', txt)
    txt = re.sub(r'[íìïî]', 'i', txt)
    txt = re.sub(r'[óòöô]', 'o', txt)
    txt = re.sub(r'[úùüû]', 'u', txt)
    txt = re.sub(r'[^a-z0-9 ]', ' ', txt)
    return " ".join(txt.split())

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

def extraer_color(valor):
    v = str(valor).lower()
    if "rojo" in v or "red" in v: return "rojo"
    if "naranja" in v or "orange" in v: return "naranja"
    if "amarill" in v or "yellow" in v: return "amarillo"
    return "verde"

def obtener_datos_alertas_smn():
    """Descarga las alertas en formato JSON o GeoJSON directo del SMN."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.smn.gob.ar/"
    }

    # 1. Intentar descargar capa GeoJSON directa con polígonos
    urls_geojson = [
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos_hoy.geojson",
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson",
        "https://ws.smn.gob.ar/alerts/type/AL/polygons"
    ]
    for u in urls_geojson:
        try:
            r = requests.get(u, headers=headers, timeout=10)
            if r.status_code == 200 and r.text.strip():
                j = r.json()
                if "features" in j and len(j["features"]) > 0:
                    print(f"[✓] Polígonos GeoJSON descargados desde: {u}")
                    return {"tipo": "geojson", "datos": j}
        except Exception:
            pass

    # 2. Descargar API estándar de alertas
    urls_api = [
        "https://ws.smn.gob.ar/alerts/type/AL",
        "https://ssl.smn.gob.ar/ws/index.php?hh=0&s=1"
    ]
    for u in urls_api:
        try:
            r = requests.get(u, headers=headers, timeout=10)
            if r.status_code == 200 and r.text.strip():
                j = r.json()
                if isinstance(j, list) and len(j) > 0:
                    print(f"[✓] Alertas de API descargadas desde: {u} ({len(j)} alertas)")
                    return {"tipo": "api", "datos": j}
        except Exception:
            pass

    # 3. Fallback: archivos locales
    for archivo in ["alertas_sat_detalle.json", "alertas_por_provincia.json"]:
        p = os.path.join(base_dir, archivo)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    c = f.read().strip()
                    if c:
                        d = json.loads(c)
                        print(f"[✓] Fallback local cargado desde: {archivo}")
                        return {"tipo": "local", "datos": d}
            except Exception:
                pass

    print("[-] No se encontraron alertas en vivo ni locales.")
    return {"tipo": "vacio", "datos": []}

def construir_mapa_alertas(paquete_alertas, dia_idx):
    """Genera un diccionario normalizado con el nivel de alerta por zona/provincia."""
    mapa = {}
    if paquete_alertas["tipo"] in ["api", "local"]:
        items = paquete_alertas["datos"]
        if isinstance(items, dict):
            items = items.get("alertas", [])

        for item in items:
            if not isinstance(item, dict): continue

            # Extraer color/severidad
            c = extraer_color(item.get("severity") or item.get("color") or item.get("nivel") or item.get("description") or "")
            if c == "verde": continue
            prio = PESO_SEVERIDAD.get(c, 1)

            # Extraer zonas o provincias
            zonas = item.get("zones", {})
            if isinstance(zonas, dict):
                for cod, znom in zonas.items():
                    zn = normalizar(znom)
                    if zn: mapa[zn] = max(mapa.get(zn, 1), prio)
            elif isinstance(zonas, list):
                for z in zonas:
                    zn = normalizar(str(z))
                    if zn: mapa[zn] = max(mapa.get(zn, 1), prio)

            # Nombre de provincia / departamento genérico
            p = normalizar(item.get("provincia") or item.get("name") or "")
            z = normalizar(item.get("zona") or item.get("departamento") or "")
            if p: mapa[p] = max(mapa.get(p, 1), prio)
            if z: mapa[z] = max(mapa.get(z, 1), prio)

    print(f"[LOG] {len(mapa)} zonas/reglas activas procesadas para colorear el mapa.")
    return mapa

def determinar_color_departamento(depto, prov, mapa_alertas):
    if not mapa_alertas:
        return "#15803d"  # Verde base

    d_norm = normalizar(depto)
    p_norm = normalizar(prov)

    prio_max = 1

    # Búsqueda por coincidencia
    for k, prio in mapa_alertas.items():
        if not k: continue
        # Coincide si el departamento o provincia está en la regla o viceversa
        if k in d_norm or d_norm in k or k in p_norm:
            if prio > prio_max:
                prio_max = prio

    inversa = {4: "rojo", 3: "naranja", 2: "amarillo", 1: "verde"}
    c = inversa[prio_max]
    if c != "verde":
        print(f"[PINTADO] {prov} -> {depto}: {c.upper()}")
    return COLORES_SAT[c]

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

def renderizar_mapa_region(region, dia_idx, ruta_temp, paquete_alertas, mapa_alertas):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Descarga departamentos IGN
    url_deptos = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url_deptos, timeout=15)
        deptos_geojson = r.json() if r.status_code == 200 else {"features": []}
    except Exception:
        deptos_geojson = {"features": []}

    # 1. Dibujar departamentos pintados
    for feat in deptos_geojson.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        depto = prop.get("departamento", "")
        prov = prop.get("provincia", "")

        color = determinar_color_departamento(depto, prov, mapa_alertas)
        dibujar_geom(ax, geom, fill_color=color, edge_color="#1e293b", lw=0.5, alpha=0.9)

    # 2. Si vino en formato GeoJSON oficial directo con polígonos, superponer
    if paquete_alertas["tipo"] == "geojson":
        for feat in paquete_alertas["datos"].get("features", []):
            prop = feat.get("properties", {})
            c = extraer_color(prop.get("color") or prop.get("nivel") or prop.get("severity") or "")
            if c != "verde":
                try:
                    g = shape(feat["geometry"])
                    dibujar_geom(ax, g, fill_color=COLORES_SAT[c], edge_color="#ffffff", lw=1.0, alpha=0.88)
                except Exception:
                    pass

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

    print(f"\n{'='*50}\n[+] Generando placas para {dia_str.upper()}...\n{'='*50}")
    paquete_alertas = obtener_datos_alertas_smn()
    mapa_alertas = construir_mapa_alertas(paquete_alertas, idx_dia)

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, paquete_alertas, mapa_alertas)

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
