import sys
sys.stdout.reconfigure(encoding='utf-8')

from binance.client import Client
from dotenv import load_dotenv
import os
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('obchody.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger()

load_dotenv()

klient = Client(
    os.getenv("BINANCE_API_KEY"),
    os.getenv("BINANCE_SECRET_KEY"),
    testnet=True
)

SYMBOL = "BTCUSDT"       # obchodujeme BTC za USDT
RSI_PERIODA = 14         # standardní nastavení RSI
RSI_KOUPIT = 30          # pod touto hodnotou kupujeme
RSI_PRODAT = 70          # nad touto hodnotou prodáváme
CASTKA_USDT = 100        # kolik USDT investujeme do jednoho obchodu
STOP_LOSS_PROCENT = 2.0  # prodej pokud cena klesne o více než 2% pod průměrnou nákupní cenu

# Postupné nakupování — rozdělíme částku do 3 nákupů při různých úrovních RSI
UROVNE_NAKUPU = [
    (30, CASTKA_USDT / 3),   # RSI < 30 → koupím třetinu
    (25, CASTKA_USDT / 3),   # RSI < 25 → koupím další třetinu
    (20, CASTKA_USDT / 3),   # RSI < 20 → koupím poslední třetinu
]


def ziskej_ceny(symbol, limit=100):
    """Stáhne posledních 'limit' zavíracích cen svíček (1 minuta)."""
    svicky = klient.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=limit)
    return [float(s[4]) for s in svicky]  # index 4 = zavírací cena


def vypocitej_rsi(ceny, perioda=14):
    """Vypočítá RSI z pole cen."""
    zisky = []
    ztraty = []

    for i in range(1, perioda + 1):
        zmena = ceny[i] - ceny[i - 1]
        if zmena > 0:
            zisky.append(zmena)
            ztraty.append(0)
        else:
            zisky.append(0)
            ztraty.append(abs(zmena))

    prumerny_zisk = sum(zisky) / perioda
    prumerna_ztrata = sum(ztraty) / perioda

    if prumerna_ztrata == 0:
        return 100  # trh jen roste, RSI = 100

    rs = prumerny_zisk / prumerna_ztrata
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def ziskej_zustatek(mena):
    """Vrátí aktuální zůstatek dané měny."""
    ucet = klient.get_account()
    for z in ucet['balances']:
        if z['asset'] == mena:
            return float(z['free'])
    return 0.0


def nakup_btc(castka_usdt):
    """Nakoupí BTC za zadanou částku USDT."""
    cena = float(klient.get_symbol_ticker(symbol=SYMBOL)['price'])
    mnozstvi = round(castka_usdt / cena, 5)
    obchod = klient.order_market_buy(symbol=SYMBOL, quantity=mnozstvi)
    return obchod


def prodej_btc(mnozstvi_btc):
    """Prodá zadané množství BTC."""
    mnozstvi = round(mnozstvi_btc, 5)
    obchod = klient.order_market_sell(symbol=SYMBOL, quantity=mnozstvi)
    return obchod


def main():
    log.info("=== Binance RSI Bot spuštěn ===")
    log.info(f"Symbol: {SYMBOL} | RSI koupit: <{RSI_KOUPIT} | RSI prodat: >{RSI_PRODAT}")
    print("Stiskni Ctrl+C pro ukončení\n")

    nakoupeno_btc = 0.0       # kolik BTC nakoupil tento bot celkem
    utraceno_usdt = 0.0       # kolik USDT jsme celkem investovali
    prumerna_nakupni_cena = 0.0  # průměrná cena za kterou jsme nakoupili
    splnene_urovne = set()    # které úrovně nákupu už byly použity (30, 25, 20)
    pocet_obchodu = 0
    celkovy_zisk = 0.0

    while True:
        try:
            ceny = ziskej_ceny(SYMBOL)
            rsi = vypocitej_rsi(ceny)
            aktualni_cena = ceny[-1]
            usdt = ziskej_zustatek("USDT")
            btc = ziskej_zustatek("BTC")
            hodnota_portfolia = usdt + (btc * aktualni_cena)

            log.info(
                f"BTC: {aktualni_cena:.2f} USDT | RSI: {rsi} | "
                f"Nakoupeno tímto botem: {nakoupeno_btc:.5f} BTC | "
                f"Volné USDT: {usdt:.2f} | Portfolio celkem: {hodnota_portfolia:.2f} USDT"
            )

            # Postupné nakupování — projdeme všechny úrovně
            for hranice_rsi, castka in UROVNE_NAKUPU:
                if rsi < hranice_rsi and hranice_rsi not in splnene_urovne and usdt >= castka:
                    log.info(f"  → RSI={rsi} je pod {hranice_rsi} → KUPUJI za {castka:.2f} USDT")
                    obchod = nakup_btc(castka)
                    nakoupene = float(obchod['executedQty'])
                    nakoupeno_btc += nakoupene
                    utraceno_usdt += castka
                    prumerna_nakupni_cena = utraceno_usdt / nakoupeno_btc
                    splnene_urovne.add(hranice_rsi)
                    stop_loss_cena = prumerna_nakupni_cena * (1 - STOP_LOSS_PROCENT / 100)
                    log.info(f"  ✓ Nákup proveden: {nakoupene:.5f} BTC | Celkem nakoupeno: {nakoupeno_btc:.5f} BTC | Stop-loss: {stop_loss_cena:.2f} USDT")

            # Stop-loss — prodej pokud cena klesla příliš
            if nakoupeno_btc > 0 and prumerna_nakupni_cena > 0:
                stop_loss_cena = prumerna_nakupni_cena * (1 - STOP_LOSS_PROCENT / 100)
                if aktualni_cena < stop_loss_cena:
                    zisk = (nakoupeno_btc * aktualni_cena) - utraceno_usdt
                    celkovy_zisk += zisk
                    pocet_obchodu += 1
                    log.info(f"  ⚠ STOP-LOSS: cena {aktualni_cena:.2f} klesla pod {stop_loss_cena:.2f} → PRODÁVÁM {nakoupeno_btc:.5f} BTC")
                    prodej_btc(nakoupeno_btc)
                    log.info(f"  ✓ Stop-loss prodej proveden | Ztráta: {zisk:+.2f} USDT")
                    log.info(f"  📊 Celkem obchodů: {pocet_obchodu} | Celkový zisk: {celkovy_zisk:+.2f} USDT")
                    nakoupeno_btc = 0.0
                    utraceno_usdt = 0.0
                    prumerna_nakupni_cena = 0.0
                    splnene_urovne = set()

            # Prodej — až RSI stoupne nad 70 a máme co prodávat
            if rsi > RSI_PRODAT and nakoupeno_btc > 0:
                trzba = nakoupeno_btc * aktualni_cena
                zisk = trzba - utraceno_usdt
                celkovy_zisk += zisk
                pocet_obchodu += 1
                log.info(f"  → RSI={rsi} je nad {RSI_PRODAT} → PRODÁVÁM {nakoupeno_btc:.5f} BTC")
                prodej_btc(nakoupeno_btc)
                log.info(f"  ✓ Prodej proveden | Zisk z obchodu: {zisk:+.2f} USDT")
                log.info(f"  📊 Celkem obchodů: {pocet_obchodu} | Celkový zisk: {celkovy_zisk:+.2f} USDT")
                nakoupeno_btc = 0.0
                utraceno_usdt = 0.0
                prumerna_nakupni_cena = 0.0
                splnene_urovne = set()

            elif nakoupeno_btc == 0 and not any(rsi < h for h, _ in UROVNE_NAKUPU):
                log.info(f"  → Čekám na signál...")
            elif nakoupeno_btc > 0:
                log.info(f"  → Držím pozici, čekám na RSI > {RSI_PRODAT}")
            else:
                log.info(f"  → Čekám na signál...")

            time.sleep(60)  # čekáme 1 minutu před dalším vyhodnocením

        except KeyboardInterrupt:
            log.info(f"\nBot ukončen. Celkem obchodů: {pocet_obchodu} | Celkový zisk: {celkovy_zisk:+.2f} USDT")
            break
        except Exception as e:
            log.error(f"  ✗ Chyba: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
