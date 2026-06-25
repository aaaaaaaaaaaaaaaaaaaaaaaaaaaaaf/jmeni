import sys
sys.stdout.reconfigure(encoding='utf-8')

import re
from datetime import datetime

SOUBOR = "obchody.log"

def nacti_obchody(soubor):
    """Přečte log a vrátí seznam obchodů."""
    nakupy = []
    prodeje = []
    zisky = []

    try:
        with open(soubor, encoding='utf-8') as f:
            radky = f.readlines()
    except FileNotFoundError:
        print(f"Soubor {soubor} nenalezen. Spusť nejdříve bota.")
        return

    for radek in radky:
        if "KUPUJI za" in radek:
            castka = re.search(r"KUPUJI za ([\d.]+) USDT", radek)
            if castka:
                nakupy.append(float(castka.group(1)))

        if "Zisk po poplatcích:" in radek or "Zisk z obchodu:" in radek:
            zisk = re.search(r"Zisk.*?: ([+-]?[\d.]+) USDT", radek)
            if zisk:
                zisky.append(float(zisk.group(1)))

        if "PRODÁVÁM" in radek or "Stop-loss prodej" in radek:
            prodeje.append(radek.strip())

    print("=" * 50)
    print("       STATISTIKA OBCHODŮ")
    print("=" * 50)
    print(f"Celkem nákupů:          {len(nakupy)}")
    print(f"Celkem prodejů:         {len(zisky)}")
    print(f"Celkem investováno:     {sum(nakupy):.2f} USDT")

    if zisky:
        celkovy_zisk = sum(zisky)
        prumerny_zisk = celkovy_zisk / len(zisky)
        nejlepsi = max(zisky)
        nejhorsi = min(zisky)
        ziskove = len([z for z in zisky if z > 0])
        ztratove = len([z for z in zisky if z <= 0])

        print(f"\nCelkový zisk:           {celkovy_zisk:+.4f} USDT")
        print(f"Průměrný zisk/obchod:   {prumerny_zisk:+.4f} USDT")
        print(f"Nejlepší obchod:        {nejlepsi:+.4f} USDT")
        print(f"Nejhorší obchod:        {nejhorsi:+.4f} USDT")
        print(f"Ziskové obchody:        {ziskove} ({ziskove/len(zisky)*100:.0f}%)")
        print(f"Ztrátové obchody:       {ztratove} ({ztratove/len(zisky)*100:.0f}%)")
    else:
        print("\nZatím žádné uzavřené obchody.")

    print("=" * 50)


if __name__ == "__main__":
    nacti_obchody(SOUBOR)
