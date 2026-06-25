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
MA_KRATKA = 20           # rychlý klouzavý průměr (posledních 20 svíček)
MA_DLOUHA = 50           # pomalý klouzavý průměr (posledních 50 svíček)
POPLATEK_PROCENT = 0.1   # Binance poplatek za obchod (0.1% z hodnoty)

# Postupné nakupování — rozdělíme částku do 3 nákupů při různých úrovních RSI
UROVNE_NAKUPU = [
    (30, CASTKA_USDT / 3),   # RSI < 30 → koupím třetinu
    (25, CASTKA_USDT / 3),   # RSI < 25 → koupím další třetinu
    (20, CASTKA_USDT / 3),   # RSI < 20 → koupím poslední třetinu
]


def poplatky_za_obchod(castka_usdt):
    """Vrátí celkové poplatky za nákup + prodej dané částky."""
    return castka_usdt * (POPLATEK_PROCENT / 100) * 2  # nákup + prodej


def ma_smysl_obchodovat(castka_usdt, ocekavany_zisk_procent):
    """Vrátí True pokud očekávaný zisk pokryje poplatky."""
    poplatky = poplatky_za_obchod(castka_usdt)
    ocekavany_zisk = castka_usdt * (ocekavany_zisk_procent / 100)
    return ocekavany_zisk > poplatky


def vypocitej_ma(ceny, perioda):
    """Vypočítá klouzavý průměr z posledních 'perioda' cen."""
    return sum(ceny[-perioda:]) / perioda


def ziskej_ceny(symbol, interval, limit=100):
    """Stáhne posledních 'limit' zavíracích cen svíček daného intervalu."""
    svicky = klient.get_klines(symbol=symbol, interval=interval, limit=limit)
    return [float(s[4]) for s in svicky]  # index 4 = zavírací cena


def trend_rostouci(symbol, interval, limit=50):
    """Vrátí True pokud MA20 > MA50 na daném časovém rámci."""
    ceny = ziskej_ceny(symbol, interval, limit=limit)
    ma20 = vypocitej_ma(ceny, 20)
    ma50 = vypocitej_ma(ceny, 50)
    return ma20 > ma50, ma20, ma50


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
            ceny = ziskej_ceny(SYMBOL, Client.KLINE_INTERVAL_1MINUTE, limit=100)
            rsi = vypocitej_rsi(ceny)
            ma_kratka = vypocitej_ma(ceny, MA_KRATKA)
            ma_dlouha = vypocitej_ma(ceny, MA_DLOUHA)
            trend_1m = ma_kratka > ma_dlouha
            trend_1h, ma20_1h, ma50_1h = trend_rostouci(SYMBOL, Client.KLINE_INTERVAL_1HOUR)
            trend_1d, ma20_1d, ma50_1d = trend_rostouci(SYMBOL, Client.KLINE_INTERVAL_1DAY)
            vsechny_trendy_nahoru = trend_1m and trend_1h and trend_1d
            aktualni_cena = ceny[-1]
            usdt = ziskej_zustatek("USDT")
            btc = ziskej_zustatek("BTC")
            hodnota_portfolia = usdt + (btc * aktualni_cena)

            def t(trend): return "↑" if trend else "↓"
            log.info(
                f"BTC: {aktualni_cena:.2f} USDT | RSI: {rsi} | "
                f"Trendy: 1m={t(trend_1m)} 1h={t(trend_1h)} 1d={t(trend_1d)} | "
                f"Nakoupeno: {nakoupeno_btc:.5f} BTC | Volné USDT: {usdt:.2f} | Portfolio: {hodnota_portfolia:.2f} USDT"
            )

            # Postupné nakupování — jen pokud je trend rostoucí
            for hranice_rsi, castka in UROVNE_NAKUPU:
                if rsi < hranice_rsi and hranice_rsi not in splnene_urovne and usdt >= castka and vsechny_trendy_nahoru:
                    poplatky = poplatky_za_obchod(castka)
                    # RSI pod 25 = očekáváme alespoň 0.5% zisk, pod 30 = alespoň 0.3%
                    ocekavany_zisk_procent = 0.5 if hranice_rsi <= 25 else 0.3
                    if not ma_smysl_obchodovat(castka, ocekavany_zisk_procent):
                        log.info(f"  → Přeskakuji — poplatky ({poplatky:.3f} USDT) by převýšily očekávaný zisk")
                        continue
                    log.info(f"  → RSI={rsi} je pod {hranice_rsi} → KUPUJI za {castka:.2f} USDT (poplatky: {poplatky:.3f} USDT)")
                    obchod = nakup_btc(castka)
                    nakoupene = float(obchod['executedQty'])
                    nakoupeno_btc += nakoupene
                    utraceno_usdt += castka + (castka * POPLATEK_PROCENT / 100)  # včetně poplatku za nákup
                    prumerna_nakupni_cena = utraceno_usdt / nakoupeno_btc
                    splnene_urovne.add(hranice_rsi)
                    stop_loss_cena = prumerna_nakupni_cena * (1 - STOP_LOSS_PROCENT / 100)
                    log.info(f"  ✓ Nákup proveden: {nakoupene:.5f} BTC | Celkem nakoupeno: {nakoupeno_btc:.5f} BTC | Stop-loss: {stop_loss_cena:.2f} USDT")

            # Stop-loss — prodej pokud cena klesla příliš
            if nakoupeno_btc > 0 and prumerna_nakupni_cena > 0:
                stop_loss_cena = prumerna_nakupni_cena * (1 - STOP_LOSS_PROCENT / 100)
                if aktualni_cena < stop_loss_cena:
                    trzba_sl = nakoupeno_btc * aktualni_cena
                    poplatek_sl = trzba_sl * POPLATEK_PROCENT / 100
                    zisk = trzba_sl - poplatek_sl - utraceno_usdt
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
                poplatek_prodej = trzba * POPLATEK_PROCENT / 100
                zisk = trzba - poplatek_prodej - utraceno_usdt  # utraceno_usdt už obsahuje poplatek za nákup
                celkovy_zisk += zisk
                pocet_obchodu += 1
                log.info(f"  → RSI={rsi} je nad {RSI_PRODAT} → PRODÁVÁM {nakoupeno_btc:.5f} BTC")
                prodej_btc(nakoupeno_btc)
                log.info(f"  ✓ Prodej proveden | Zisk po poplatcích: {zisk:+.2f} USDT")
                log.info(f"  📊 Celkem obchodů: {pocet_obchodu} | Celkový zisk po poplatcích: {celkovy_zisk:+.2f} USDT")
                nakoupeno_btc = 0.0
                utraceno_usdt = 0.0
                prumerna_nakupni_cena = 0.0
                splnene_urovne = set()

            elif nakoupeno_btc > 0:
                log.info(f"  → Držím pozici, čekám na RSI > {RSI_PRODAT}")
            elif not vsechny_trendy_nahoru:
                duvod = []
                if not trend_1m: duvod.append("1m ↓")
                if not trend_1h: duvod.append("1h ↓")
                if not trend_1d: duvod.append("1d ↓")
                log.info(f"  → Nekupuji — klesající trend: {', '.join(duvod)}")
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
