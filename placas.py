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

REGIONES_LIMITES = {
    "Norte": {"minx": -69.5, "maxx": -53.0, "miny": -31.5, "maxy": -21.5},
    "Centro": {"minx": -71.5, "maxx": -56.0, "miny": -42.0, "maxy": -30.0},
    "Sur": {"minx": -75.0, "maxx": -62.0, "miny": -55.5, "maxy": -40.0}
}

COLORES_HEX = {
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
    txt = re.sub(r'[^a-z0-9]', '', txt)
    return txt

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

def extraer_color(valor):
    val = str(valor).lower()
    if any(k in val for k in ["rojo", "red"]): return "rojo"
    if any(k in val for k in ["naranja", "orange"]): return "naranja"
    if any(k in val for k in ["amarillo", "yellow"]): return "amarillo"
    return "verde"

def cargar_todas_las_alertas(dia_idx):
    """
    Lee todos los JSON disponibles en el repositorio y consolida un mapa
    de búsqueda por provincia y zona.
    """
    mapa_alertas = {}  # clave: texto normalizado, valor: max severidad
    archivos = ["alertas_sat_detalle.json", "alertas_por_provincia.json", "alertas_completas.json"]
    claves_dia = [str(dia_idx), ["hoy", "manana", "pasado"][dia_idx]]

    for nom in archivos:
        path = os.path.join(base_dir, nom)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Si es diccionario organizado por día
            if isinstance(data, dict):
                sub_data = None
                for kd in claves_dia:
                    if kd in data:
                        sub_data = data[kd]
                        break
                items = sub_data if sub_data is not None else data.values()
            elif isinstance(data, list):
                items = data
            else:
                items = []

            for elem in items:
                if isinstance(elem, dict):
                    # Verificar día si viene explícito
                    item_dia = elem.get("dia")
                    if item_dia is not None and str(item_dia) not in claves_dia and item_dia != dia_idx:
                        continue

                    color = extraer_color(elem.get("color") or elem.get("nivel") or elem.get("estado") or elem.get("severidad"))
                    if color == "verde":
                        continue

                    prio = PESO_SEVERIDAD.get(color, 1)

                    # Registrar por provincia
                    p = normalizar_texto(elem.get("provincia") or elem.get("name") or "")
                    if p:
                        mapa_alertas[p] = max(mapa_alertas.get(p, 1), prio)

                    # Registrar por departamento o zona
                    z = normalizar_texto(elem.get("zona") or elem.get("departamento") or elem.get("nombre") or "")
                    if z:
                        mapa_alertas[z] = max(mapa_alertas.get(z, 1), prio)

                elif isinstance(elem, list):
                    # Sublistas
                    for sub in elem:
                        if isinstance(sub, dict):
                            color = extraer_color(sub.get("color") or sub.get("nivel"))
                            prio = PESO_SEVERIDAD.get(color, 1)
                            p = normalizar_texto(sub.get("provincia") or "")
                            z = normalizar_texto(sub.get("zona") or sub.get("departamento") or "")
                            if p: mapa_alertas[p] = max(mapa_alertas.get(p, 1), prio)
                            if z: mapa_alertas[z] = max(mapa_alertas.get(z, 1), prio)

        except Exception as e:
            print(f"[-] Error parseando {nom}: {e}")

    print(f"[+] Reglas de alerta detectadas para día {dia_idx}: {len(mapa_alertas)} áreas registradas.")
    return mapa_alertas

def determinar_color_depto(depto_raw, prov_raw, mapa_alertas):
    if not mapa_alertas:
        return "#14532d"  # Verde base

    d_norm = normalizar_texto(depto_raw)
    p_norm = normalizar_texto(prov_raw)

    prio_max = 1

    # Chequear coincidencia exacta o parcial de departamento
    for k, prio in mapa_alertas.items():
        if k and (k in d_norm or d_norm in k or k in p_norm or p_norm in k):
            if prio > prio_max:
                prio_max = prio

    inversa = {4: "rojo", 3: "naranja", 2: "amarillo", 1: "verde"}
    return COLORES_HEX[inversa[prio_max]]

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

def renderizar_mapa_region(region, dia_idx, ruta_temp, mapa_alertas):
    fig, ax = plt.subplots(figsize=(8, 7), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    url_deptos = "https://raw.githubusercontent.com/mgaitan/departamentos_argentina/master/departamentos-argentina.json"
    try:
        r = requests.get(url_deptos, timeout=15)
        deptos_geojson = r.json() if r.status_code == 200 else {"features": []}
    except Exception:
        deptos_geojson = {"features": []}

    # Pintar cada departamento cruzando con las alertas consolidadas
    for feat in deptos_geojson.get("features", []):
        geom = shape(feat["geometry"])
        prop = feat.get("properties", {})
        depto = prop.get("departamento", "")
        prov = prop.get("provincia", "")

        color = determinar_color_depto(depto, prov, mapa_alertas)
        dibujar_geom(ax, geom, fill_color=color, edge_color="#1e293b", lw=0.6, alpha=0.92)

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
    mapa_alertas = cargar_todas_las_alertas(idx_dia)

    for region in ["Norte", "Centro", "Sur"]:
        nombre_salida = f"Alerta_{prefijo}_{region}.png"
        ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)
        ruta_mapa_temp = os.path.join(base_dir, f"temp_{nombre_salida}")

        renderizar_mapa_region(region, idx_dia, ruta_mapa_temp, mapa_alertas)

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
