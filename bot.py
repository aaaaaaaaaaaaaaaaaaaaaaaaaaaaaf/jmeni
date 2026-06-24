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

    ma_pozici = False  # bot zatím nic nekoupil

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
                f"Mám: {btc:.5f} BTC (= {btc * aktualni_cena:.2f} USDT) | "
                f"Volné USDT: {usdt:.2f} | Portfolio celkem: {hodnota_portfolia:.2f} USDT"
            )

            if rsi < RSI_KOUPIT and not ma_pozici and usdt >= CASTKA_USDT:
                log.info(f"  → RSI={rsi} je pod {RSI_KOUPIT} → KUPUJI za {CASTKA_USDT} USDT")
                nakup_btc(CASTKA_USDT)
                ma_pozici = True
                log.info(f"  ✓ Nákup proveden")

            elif rsi > RSI_PRODAT and ma_pozici and btc > 0:
                log.info(f"  → RSI={rsi} je nad {RSI_PRODAT} → PRODÁVÁM {btc:.5f} BTC")
                prodej_btc(btc)
                ma_pozici = False
                log.info(f"  ✓ Prodej proveden")

            else:
                log.info(f"  → Čekám na signál...")

            time.sleep(60)  # čekáme 1 minutu před dalším vyhodnocením

        except KeyboardInterrupt:
            log.info("\nBot ukončen.")
            break
        except Exception as e:
            log.error(f"  ✗ Chyba: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
