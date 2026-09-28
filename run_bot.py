import sys
import placas

def main():
    print("Iniciando generación automática de placas SMN...")
    # Genera placas para Hoy (0), Mañana (1) y Pasado mañana (2)
    for dia in [0, 1, 2]:
        try:
            print(f"\n--- Procesando día índice {dia} ---")
            placas.procesar_generacion(dia)
        except Exception as e:
            print(f"Error procesando día {dia}: {e}", file=sys.stderr)
    print("\nProceso finalizado con éxito.")

if __name__ == "__main__":
    main()