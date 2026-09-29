import os
import sys
import json
import requests
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import contextily as ctx
from shapely.geometry import shape, MultiPolygon
from PIL import Image, ImageDraw, ImageFont

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CARPETA_SALIDA = os.path.join(base_dir, "placas_mapa")
os.makedirs(CARPETA_SALIDA, exist_ok=True)

# Resolución de la placa
ANCHO_PLACA = 1080
ALTO_PLACA = 1080

# Colores del tema SATEM
COLOR_FONDO = (10, 15, 30)       # Azul muy oscuro
COLOR_CAJA_GRIS = (20, 25, 45)   # Gris azulado oscuro (para cajas)
COLOR_AMARILLO = (255, 204, 0)   # Texto amarillo SATEM
COLOR_ROJO = (220, 38, 38)       # Rojo para tormentas severas
COLOR_TEXTO_BLANCO = (255, 255, 255)
COLOR_TEXTO_GRIS = (156, 163, 175)
COLOR_BORDE = (30, 41, 59)

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
    """Dibuja un rectángulo con bordes redondeados."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def descargar_acp_smn():
    """Descarga los Avisos a Corto Plazo (ACP) vigentes del SMN."""
    url = "https://ws.smn.gob.ar/alerts/type/AC"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"[✓] {len(data)} Avisos a Corto Plazo obtenidos.")
                return data
    except Exception as e:
        print(f"[-] Error descargando ACP: {e}")
    return []

def generar_mapa_acp(poligono_wkt, ruta_temp):
    """
    Genera el mapa con fondo de OpenStreetMap y el polígono rojo semitransparente.
    Para dibujar, requiere que el WKT de la API del SMN sea convertido a polígono.
    (Simulado usando un encuadre fijo temporal si no se parsea WKT aquí).
    """
    from shapely import wkt
    import geopandas as gpd
    
    fig, ax = plt.subplots(figsize=(6, 6))
    
    try:
        # Convertir WKT del SMN a Geometría
        geom = wkt.loads(poligono_wkt)
        gdf = gpd.GeoDataFrame(index=[0], crs='epsg:4326', geometry=[geom])
        # Reproyectar a Web Mercator para usar tiles de OpenStreetMap
        gdf = gdf.to_crs(epsg=3857)
        
        # Dibujar polígono (Rojo translúcido con borde marcado)
        gdf.plot(ax=ax, facecolor='red', edgecolor='red', alpha=0.3, linewidth=2)
        
        # Dibujar puntos en los vértices
        for x, y in list(geom.exterior.coords):
            ax.plot(x, y, marker='o', color='yellow', markeredgecolor='black', markersize=6, transform=ctx.crs.WGS84_to_Mercator)
            
        # Añadir mapa base (OpenStreetMap)
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        
    except Exception as e:
        print(f"[-] Error renderizando mapa ACP: {e}")
        ax.set_facecolor('#d1d5db') # Fondo gris en caso de error

    ax.set_axis_off()
    plt.tight_layout(pad=0)
    plt.savefig(ruta_temp, dpi=150, bbox_inches='tight', pad_inches=0)
    plt.close(fig)

def crear_placa_acp(acp_data, idx):
    # Extraer datos del ACP
    # La API del SMN para AC entrega campos como issueTime, updateTime, title, description, polygon
    hora_emision = acp_data.get("updateTime", "")[-8:-3] or "12:00"
    
    # Validez de 3 horas aproximada
    try:
        hora_validez = (datetime.strptime(hora_emision, "%H:%M") + timedelta(hours=3)).strftime("%H:%M")
    except:
        hora_validez = "15:00"

    titulo_fenomeno = acp_data.get("title", "TORMENTAS FUERTES CON LLUVIAS INTENSAS.").upper()
    
    # Parsear zonas
    zonas_dict = acp_data.get("zones", {})
    provincias = {}
    for cod, desc in zonas_dict.items():
        if " - " in desc:
            prov, depto = desc.split(" - ", 1)
        else:
            prov, depto = "ZONA", desc
        
        if prov not in provincias:
            provincias[prov] = []
        provincias[prov].append(depto)

    # Crear imagen base
    img = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
    draw = ImageDraw.Draw(img)

    # 1. ENCABEZADO
    font_titulo = obtener_fuente(40, bold=True)
    font_sub = obtener_fuente(20)
    
    # Simulación del logo a la izquierda (Circulo blanco temporal)
    draw.ellipse([(40, 30), (120, 110)], fill=(255, 255, 255))
    draw.text((150, 40), "SATEM ARGENTINA", font=font_titulo, fill=COLOR_TEXTO_BLANCO)
    draw.text((150, 85), "Soporte y Alerta Temprana ante Eventos Meteorológicos", font=font_sub, fill=(56, 189, 248))

    # Título AVISO A CORTO PLAZO
    font_acp = obtener_fuente(35, bold=True)
    draw.text((40, 140), "AVISO A CORTO PLAZO", font=font_acp, fill=COLOR_AMARILLO)

    # 2. CAJAS DE HORA
    # Caja Emisión
    dibujar_caja_redondeada(draw, [(40, 190), (250, 280)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((75, 205), "HORA DE EMISIÓN", font=obtener_fuente(14), fill=COLOR_TEXTO_GRIS)
    draw.text((65, 235), f"{hora_emision} HS", font=obtener_fuente(28, bold=True), fill=COLOR_TEXTO_BLANCO)

    # Caja Validez
    dibujar_caja_redondeada(draw, [(270, 190), (480, 280)], fill=COLOR_CAJA_GRIS, outline=COLOR_AMARILLO, width=2)
    draw.text((310, 205), "VÁLIDO HASTA", font=obtener_fuente(14), fill=COLOR_AMARILLO)
    draw.text((300, 235), f"{hora_validez} HS", font=obtener_fuente(28, bold=True), fill=COLOR_AMARILLO)

    # 3. CAJA FENÓMENO (Rojo)
    dibujar_caja_redondeada(draw, [(40, 310), (480, 520)], fill=(40, 15, 20), outline=COLOR_ROJO, width=2)
    draw.text((60, 330), "FENÓMENO PREVISTO", font=obtener_fuente(14, bold=True), fill=COLOR_ROJO)
    
    import textwrap
    lines = textwrap.wrap(titulo_fenomeno, width=25)
    y_text = 370
    for line in lines:
        draw.text((60, y_text), line, font=obtener_fuente(24, bold=True), fill=COLOR_TEXTO_BLANCO)
        y_text += 35

    # 4. CAJA ZONAS
    dibujar_caja_redondeada(draw, [(40, 540), (480, 850)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((60, 560), "ZONAS BAJO ALERTA", font=obtener_fuente(14, bold=True), fill=(56, 189, 248))
    
    y_zona = 600
    for prov, deptos in provincias.items():
        draw.text((60, y_zona), f"{prov}:", font=obtener_fuente(24, bold=True), fill=COLOR_AMARILLO)
        y_zona += 35
        depto_str = " • ".join(deptos) + "."
        lines_d = textwrap.wrap(depto_str, width=32)
        for ld in lines_d:
            draw.text((60, y_zona), ld, font=obtener_fuente(20, bold=True), fill=COLOR_TEXTO_BLANCO)
            y_zona += 28
        y_zona += 10

    # 5. CAJA RECOMENDACIONES (Abajo)
    dibujar_caja_redondeada(draw, [(40, 870), (1040, 980)], fill=COLOR_CAJA_GRIS, outline=COLOR_BORDE, width=2)
    draw.text((60, 890), "MEDIDAS DE PREVENCIÓN INMEDIATA", font=obtener_fuente(14, bold=True), fill=(56, 189, 248))
    draw.text((60, 920), "• Permanezca en construcciones cerradas y asegure objetos que puedan volarse.", font=obtener_fuente(16), fill=COLOR_TEXTO_GRIS)
    draw.text((60, 945), "• No circule por calles anegadas y manténgase alejado de postes y árboles.", font=obtener_fuente(16), fill=COLOR_TEXTO_GRIS)

    # 6. MAPA
    # Descargar mapa y pegarlo
    ruta_mapa_temp = os.path.join(base_dir, f"temp_mapa_{idx}.png")
    wkt_poly = acp_data.get("polygon", "")
    if wkt_poly:
        generar_mapa_acp(wkt_poly, ruta_mapa_temp)
        
        if os.path.exists(ruta_mapa_temp):
            with Image.open(ruta_mapa_temp) as map_img:
                map_img = map_img.resize((530, 660), Image.Resampling.LANCZOS)
                # Borde rojo del mapa
                draw.rectangle([(508, 188), (1042, 852)], outline=COLOR_ROJO, width=2)
                img.paste(map_img, (510, 190))
            os.remove(ruta_mapa_temp)

    # Footer
    draw.text((40, 1020), "Datos oficiales: Servicio Meteorológico Nacional (SMN)", font=obtener_fuente(12), fill=(75, 85, 99))

    # Guardar
    ruta_salida = os.path.join(CARPETA_SALIDA, f"ACP_{idx}.png")
    img.save(ruta_salida, format="PNG")
    print(f"[✓] Placa ACP guardada: {ruta_salida}")

if __name__ == "__main__":
    acps = descargar_acp_smn()
    if not acps:
        print("[!] No hay Avisos a Corto Plazo vigentes en el SMN en este momento.")
    else:
        for i, acp in enumerate(acps):
            crear_placa_acp(acp, i)
