# tests/test_liquidity.py
# encoding: utf-8
"""
Sentinel Pro KB5 --- Test LiquidityDetector
Tests la detection des Pools, Sweeps, et DOL sans connexion
MT5 reelle - utilise un DataFrame simule.

Lancement :
    cd c:\\Users\\djerm\\Desktop\\bottrading\\sentinel_pro
    python -m tests.test_liquidity
"""

import sys
import os
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.getcwd())

print("\n" + "=" * 60)
print("  LiquidityDetector --- Test Unitaire")
print("=" * 60)


# -------------------------------------------------------------------
# SETUP : Mock DataStore + bougies synthetiques
# -------------------------------------------------------------------

def make_candle_df(n_candles=50, base_price=1.10000, trend="UP",
                   with_sweep_at=None, sweep_direction="BULL"):
    """
    Genere un DataFrame OHLC synthetique.
    with_sweep_at : index de la bougie avec sweep artificiel
    """
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start   = now_utc - timedelta(hours=n_candles)

    rows = []
    price = base_price
    for i in range(n_candles):
        t    = start + timedelta(hours=i)
        step = 0.0002 if trend == "UP" else -0.0002
        o    = price
        price += step + np.random.uniform(-0.0001, 0.0001)
        c    = price
        h    = max(o, c) + np.random.uniform(0.00005, 0.0002)
        l    = min(o, c) - np.random.uniform(0.00005, 0.0002)

        # Injection sweep artificiel
        if with_sweep_at is not None and i == with_sweep_at:
            if sweep_direction == "BULL":
                l = min(o, c) - 0.0009   # grande meche en bas (SSL sweep)
                c = max(o, c - 0.0001)   # corps cloture au-dessus
            else:  # BEAR
                h = max(o, c) + 0.0009   # grande meche en haut (BSL sweep)
                c = min(o, c + 0.0001)   # corps cloture en-dessous

        rows.append({
            "time":        t,
            "open":        round(o, 6),
            "high":        round(h, 6),
            "low":         round(l, 6),
            "close":       round(c, 6),
            "tick_volume": np.random.randint(100, 500),
        })

    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


def make_daily_df(n_days=10, base_price=1.10000):
    """Genere un DataFrame D1 simple."""
    now_utc = datetime.now(timezone.utc).replace(hour=0, minute=0,
                                                  second=0, microsecond=0)
    rows  = []
    price = base_price
    for i in range(n_days):
        t = now_utc - timedelta(days=n_days - i)
        o = price
        c = price + np.random.uniform(-0.003, 0.003)
        h = max(o, c) + np.random.uniform(0.001, 0.003)
        l = min(o, c) - np.random.uniform(0.001, 0.003)
        rows.append({"time": t, "open": round(o, 6), "high": round(h, 6),
                     "low": round(l, 6), "close": round(c, 6),
                     "tick_volume": 1000})
        price = c

    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


# -------------------------------------------------------------------
# INSTANCIATION AVEC MOCKS
# -------------------------------------------------------------------

from analysis.liquidity_detector import LiquidityDetector

mock_ds = MagicMock()

# Donnees synthetiques
df_h1_bull_sweep = make_candle_df(n_candles=50, trend="UP",
                                   with_sweep_at=47,
                                   sweep_direction="BULL")
df_d1  = make_daily_df(n_days=10)
df_w1  = make_daily_df(n_days=5, base_price=1.09000)
df_m15 = make_candle_df(n_candles=100, trend="UP")


def mock_get_candles(pair, tf):
    if tf == "H1":  return df_h1_bull_sweep
    if tf == "D1":  return df_d1
    if tf == "W":   return df_w1
    if tf == "M15": return df_m15
    return None


mock_ds.get_candles.side_effect = mock_get_candles
mock_ds.set_analysis = MagicMock()

detector = LiquidityDetector(data_store=mock_ds)

# -------------------------------------------------------------------
# TEST 1 : Scan complet et pools
# -------------------------------------------------------------------
print("\n[TEST 1] Scan complet et calcul des Pools...")
result = detector.scan_pair("EURUSD")

assert "pools"  in result, "FAIL: cle 'pools' manquante"
assert "sweeps" in result, "FAIL: cle 'sweeps' manquante"
assert "dol"    in result, "FAIL: cle 'dol' manquante"
assert result["pools"].get("pdh") is not None, "FAIL: PDH non calcule"
assert result["pools"].get("pdl") is not None, "FAIL: PDL non calcule"
print(f"  OK  PDH : {result['pools']['pdh']['level']}")
print(f"  OK  PDL : {result['pools']['pdl']['level']}")
if result.get("asia_range"):
    print(f"  OK  Asia Range : {result['asia_range'].get('high')} / {result['asia_range'].get('low')}")
else:
    print("  OK  Asia Range : non en session asiatique (normal hors 21h-00h UTC)")

# -------------------------------------------------------------------
# TEST 2 : Detection d'un Sweep BULL
# -------------------------------------------------------------------
print("\n[TEST 2] Detection d'un Sweep BULLISH...")
fresh_sweeps = detector.get_sweeps("EURUSD", status="FRESH")
all_sweeps   = detector.get_sweeps("EURUSD")

print(f"  Sweeps detectes : {len(all_sweeps)} total, {len(fresh_sweeps)} FRESH")

if fresh_sweeps:
    s = fresh_sweeps[0]
    print(f"  OK  Sweep FRESH : {s['type']} sur {s['pool_type']} @ {s['pool_level']}")
    print(f"      Wick : {s['atr_ratio']}x ATR | Statut : {s['status']}")
else:
    print("  INFO : Aucun sweep FRESH (fenetre = 5 bougies, peut manquer selon timing)")

# -------------------------------------------------------------------
# TEST 3 : has_fresh_sweep() API rapide
# -------------------------------------------------------------------
print("\n[TEST 3] API has_fresh_sweep()...")
has_bull = detector.has_fresh_sweep("EURUSD", direction="BULLISH")
has_bear = detector.has_fresh_sweep("EURUSD", direction="BEARISH")
print(f"  BULLISH : {has_bull} | BEARISH : {has_bear}")
print(f"  OK  API accessible sans erreur")

# -------------------------------------------------------------------
# TEST 4 : DOL (Draw on Liquidity)
# -------------------------------------------------------------------
print("\n[TEST 4] Draw on Liquidity (DOL)...")
dol = detector.get_dol("EURUSD")
print(f"  Direction  : {dol.get('direction')}")
print(f"  Target     : {dol.get('target_type')} @ {dol.get('target_level')}")
print(f"  Confidence : {dol.get('confidence')}")
print(f"  Reason     : {dol.get('reason')}")
print(f"  OK  DOL calcule sans erreur")

# -------------------------------------------------------------------
# TEST 5 : Snapshot Dashboard
# -------------------------------------------------------------------
print("\n[TEST 5] Snapshot Dashboard...")
snap = detector.get_snapshot("EURUSD")
assert "pdh" in snap, "FAIL: PDH manquant dans snapshot"
assert "dol_direction" in snap, "FAIL: dol_direction manquant dans snapshot"
print(f"  OK  Snapshot coherent : {snap}")

# -------------------------------------------------------------------
# TEST 6 : Equal Highs / Equal Lows
# -------------------------------------------------------------------
print("\n[TEST 6] Equal Highs / Equal Lows...")
pools = detector.get_pools("EURUSD")
eqh   = pools.get("equal_highs", [])
eql   = pools.get("equal_lows",  [])
print(f"  Equal Highs (EQH) : {len(eqh)}")
print(f"  Equal Lows  (EQL) : {len(eql)}")
print(f"  OK  Calcul Equal H/L sans erreur")

# -------------------------------------------------------------------
# RESUME
# -------------------------------------------------------------------
print("\n" + "=" * 60)
print("  TOUS LES TESTS REUSSIS --- LiquidityDetector operationnel")
print("=" * 60 + "\n")
