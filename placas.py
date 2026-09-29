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

# Rutas y configuración de carpetas
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CARPETA_SALIDA = os.path.join(base_dir, "placas_mapa")
os.makedirs(CARPETA_SALIDA, exist_ok=True)

# Dimensiones y colores
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

# --- FUNCIONES BASE ---

def obtener_fuente(tamano, bold=False):
    fuentes_posibles = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "DejaVuSans.ttf", "arial.ttf"
    ]
    for ruta in fuentes_posibles:
        if os.path.exists(ruta):
            try: return ImageFont.truetype(ruta, tamano)
            except Exception: continue
    return ImageFont.load_default()

def extraer_nivel(val):
    val_norm = str(val).lower()
    if any(c in val_norm for c in ["rojo", "red"]): return "rojo"
    if any(c in val_norm for c in ["naranja", "orange"]): return "naranja"
    if any(c in val_norm for c in ["amarillo", "yellow"]): return "amarillo"
    return "verde"

# --- 1. DESCARGA CON CABECERAS REALES ---

def descargar_poligonos_sat(dia_idx):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.smn.gob.ar/alertas",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8"
    }
    
    sufijo = f"_{dia_idx}" if dia_idx > 0 else ""
    urls = [
        f"https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos{sufijo}.geojson",
        f"https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos{sufijo}.json",
        "https://ssl.smn.gob.ar/ws/alertas/alertas_sat_poligonos.geojson"
    ]
    
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                if "features" in data and len(data["features"]) > 0:
                    print(f"[LOG] GeoJSON remoto obtenido desde: {url} ({len(data['features'])} polígonos)")
                    return data
        except Exception:
            continue
            
    print(f"[LOG] No se pudo obtener GeoJSON remoto para el día {dia_idx}. Dependiendo exclusivamente de JSON locales...")
    return None

# --- 2. COINCIDENCIA DIFUSA (TOKEN POR TOKEN) ---

def normalizar_a_tokens(texto):
    if not texto: return set()
    txt = str(texto).lower().strip()
    txt = re.sub(r'[áàäâ]', 'a', txt)
    txt = re.sub(r'[éèëê]', 'e', txt)
    txt = re.sub(r'[íìïî]', 'i', txt)
    txt = re.sub(r'[óòöô]', 'o', txt)
    txt = re.sub(r'[úùüû]', 'u', txt)
    palabras = set(re.findall(r'[a-z0-9]{3,}', txt))
    stopwords = {"cordillera", "valles", "meseta", "costa", "zona", "norte", "sur", "este", "oeste", "centro"}
    return palabras - stopwords

def cargar_alertas_locales(dia_idx):
    reglas = []
    archivos = ["alertas_sat_detalle.json", "alertas_por_provincia.json", "alertas_completas.json"]
    claves_dia = [str(dia_idx), ["hoy", "manana", "pasado"][dia_idx]]
    
    for nom in archivos:
        path = os.path.join(base_dir, nom)
        if not os.path.exists(path): continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                for kd in claves_dia:
                    if kd in data:
                        data = data[kd]
                        break
                if isinstance(data, dict):
                    data = list(data.values())
            
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict): continue
                    
                    color = extraer_nivel(item.get("color") or item.get("nivel") or item.get("severidad"))
                    if color == "verde": continue
                    
                    prov = str(item.get("provincia") or item.get("name") or "")
                    zona = str(item.get("zona") or item.get("departamento") or item.get("nombre") or "")
                    
                    reglas.append({
                        "color": color,
                        "prio": PESO_SEVERIDAD.get(color, 1),
                        "tokens_prov": normalizar_a_tokens(prov),
                        "tokens_zona": normalizar_a_tokens(zona),
                        "texto_original": f"{prov} - {zona}".strip(" -")
                    })
        except Exception as e:
            print(f"[-] Error parseando {nom}: {e}")
            
    print(f"[LOG] {len(reglas)} reglas de alerta estructuradas leídas para el día {dia_idx}.")
    return reglas

def coincide_departamento(depto_mapa, prov_mapa, regla):
    tokens_depto = normalizar_a_tokens(depto_mapa)
    tokens_prov = normalizar_a_tokens(prov_mapa)
    
    # Coincidencia por tokens de departamento
    if tokens_depto and (tokens_depto & regla["tokens_zona"]):
        return True
    
    # Coincidencia por provincia (si la alerta no especificó departamento/zona, aplica a toda)
    if tokens_prov and (tokens_prov & regla["tokens_prov"]) and not regla["tokens_zona"]:
        return True
        
    return False

# --- 3. REGISTRO EN LOGS Y ASIGNACIÓN DE COLOR ---

def procesar_alertas_con_logs(depto_nombre, prov_nombre, reglas_alerta):
    color_asignado = "verde"
    prio_max = 1
    motivos = []

    for r in reglas_alerta:
        if coincide_departamento(depto_nombre, prov_nombre, r):
            if r["prio"] > prio_max:
                prio_max = r["prio"]
                color_asignado = r["color"]
            motivos.append(f"[{r['color'].upper()}] {r['texto_original']}")

    if color_asignado != "verde":
        print(f"[PINTADO] {prov_nombre}, {depto_nombre} -> {color_asignado.upper()} | Motivo: {', '.join(motivos)}")

    return COLORES_SAT.get(color_asignado, "#15803d")

# --- MOTOR DE DIBUJO ---

def dibujar_geom(ax, geom, color_relleno, color_borde='#0f172a', lw=0.6, alpha=0.9):
    if geom.geom_type == 'Polygon':
        x, y = geom.exterior.xy
        ax.fill(x, y, color=color_relleno, alpha=alpha)
        ax.plot(x, y, color=color_borde, linewidth=lw)
    elif geom.geom_type == 'MultiPolygon':
        for sub in geom.geoms:
            x, y = sub.exterior.xy
            ax.fill(x, y, color=color_relleno, alpha=alpha)
            ax.plot(x, y, color=color_borde, linewidth=lw)

def renderizar_mapa_region(region, dia_idx, ruta_temp, poligonos_sat, reglas_alerta):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Cartografía base de departamentos IGN
    url_deptos = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url_deptos, timeout=15)
        deptos_geojson = r.json() if r.status_code == 200 else {"features": []}
    except Exception:
        deptos_geojson = {"features": []}

    # 1. Dibujar departamentos y aplicar coincidencias difusas
    for feat in deptos_geojson.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        depto = prop.get("departamento", "")
        prov = prop.get("provincia", "")

        color_relleno = procesar_alertas_con_logs(depto, prov, reglas_alerta)
        dibujar_geom(ax, geom, color_relleno=color_relleno, color_borde="#1e293b", lw=0.5, alpha=0.85)

    # 2. Superponer polígonos del SMN si la descarga remota funcionó
    if poligonos_sat:
        for feat in poligonos_sat.get("features", []):
            prop = feat.get("properties", {})
            c_sat = extraer_nivel(prop.get("color") or prop.get("nivel") or "")
            if c_sat != "verde":
                try:
                    g = shape(feat["geometry"])
                    dibujar_geom(ax, g, color_relleno=COLORES_SAT[c_sat], color_borde="#ffffff", lw=1.0, alpha=0.9)
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

    print(f"\n{'='*50}\n[+] Procesando placas para {dia_str.upper()}...\n{'='*50}")
    poligonos_sat = descargar_poligonos_sat(idx_dia)
    reglas_alerta = cargar_alertas_locales(idx_dia)

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, poligonos_sat, reglas_alerta)

        # Composición con Pillow
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
