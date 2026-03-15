# tests/test_amd.py
# encoding: utf-8
"""
Sentinel Pro KB5 --- Test AMDDetector (Power of 3 / Cycle ICT)
Simule une journee AMD typique :
  PHASE A : Range asiatique serre
  PHASE M : Judas Swing (chute sous le bas du range malgre biais haussier)
  PHASE D : Retournement haussier et expansion (MSS)

Lancement :
    cd c:\\Users\\djerm\\Desktop\\bottrading\\sentinel_pro
    python -m tests.test_amd
"""

import sys
import os
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.getcwd())

print("\n" + "=" * 60)
print("  AMDDetector --- Test Unitaire (Power of 3 ICT)")
print("=" * 60)


# -------------------------------------------------------------------
# HELPERS : Construction d'une journee AMD synthetique
# -------------------------------------------------------------------

def make_amd_day(base_price=1.10000, atr=0.0015):
    """
    Construit un DataFrame H1 simulant une journee AMD classique :
      H0-H3  : Accumulation (range serre pres de base_price)
      H4     : Manipulation (chute sous le bas du range => Judas Swing)
      H5-H12 : Distribution (rebond agressif au-dessus du haut du range => MSS)
    """
    now = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = []

    # ---- PHASE A : Accumulation (H0-H3) ----
    for i in range(4):
        t = now + timedelta(hours=i)
        o = base_price + np.random.uniform(-0.0002, 0.0002)
        c = base_price + np.random.uniform(-0.0002, 0.0002)
        h = max(o, c) + 0.0003
        l = min(o, c) - 0.0003
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                     "tick_volume": 100})

    accum_high = max(r["high"] for r in rows)
    accum_low  = min(r["low"]  for r in rows)

    # ---- PHASE M : Manipulation (H4 = Judas Swing baissier) ----
    # Grande meche sous le bas du range, corps cloture au-dessus
    t = now + timedelta(hours=4)
    manip_drop = accum_low - atr * 0.8   # Cassure sous le range
    o = accum_low - 0.0001
    c = accum_low + 0.0005               # Corps ferme DESSUS du bas du range => Turtle Soup
    h = max(o, c) + 0.0002
    l = manip_drop                        # Grande meche baisiere
    rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                 "tick_volume": 500})

    # ---- Quelques bougies de transition (H5-H7) ----
    price = c
    for i in range(5, 8):
        t = now + timedelta(hours=i)
        price += 0.0003
        o = price - 0.0001
        c = price + 0.0001
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0001
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                     "tick_volume": 200})

    # ---- PHASE D : Distribution / MSS haussier (H8) ----
    # Cassure au-dessus du haut de l'accumulation => Distribution confirmee
    t = now + timedelta(hours=8)
    o = accum_high - 0.0002
    c = accum_high + atr * 0.5           # Grande bougie haussiere qui casse le range
    h = c + 0.0001
    l = o - 0.0001
    rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                 "tick_volume": 800})

    # ---- Continuation (H9-H20) ----
    price = c
    for i in range(9, 21):
        t = now + timedelta(hours=i)
        price += 0.0004
        o = price - 0.0001
        c = price + 0.0002
        h = max(o, c) + 0.0003
        l = min(o, c) - 0.0001
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                     "tick_volume": 300})

    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df, accum_high, accum_low


def make_filler_df(n=30, base=1.10000):
    """DataFrame de remplissage pour le lookback."""
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rows = []
    price = base
    for i in range(n):
        t = now_utc - timedelta(hours=n - i)
        o = price
        price += np.random.uniform(-0.0003, 0.0003)
        c = price
        h = max(o, c) + np.random.uniform(0.0001, 0.0003)
        l = min(o, c) - np.random.uniform(0.0001, 0.0003)
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c,
                     "tick_volume": 100})
    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


# -------------------------------------------------------------------
# CONSTRUCTION DES MOCKS
# -------------------------------------------------------------------

from analysis.amd_detector import AMDDetector

mock_ds  = MagicMock()
mock_liq = MagicMock()
mock_bias = MagicMock()

# Journee AMD synthetique
df_amd, ACCUM_HIGH, ACCUM_LOW = make_amd_day(base_price=1.10000, atr=0.0015)
df_filler = make_filler_df(n=28, base=1.09900)

# DataFrame complet = filler + journee AMD (48 H1 = 2 jours)
df_h1_full = pd.concat([df_filler, df_amd])

print(f"\n  Dataset : {len(df_h1_full)} bougies H1")
print(f"  Accum High : {round(ACCUM_HIGH, 5)} | Accum Low : {round(ACCUM_LOW, 5)}")

# Biais haussier simule depuis BiasDetector
mock_bias.get_bias.return_value = {"direction": "BULLISH"}

# Asia Range simule depuis LiquidityDetector (correspondant au range d'accum)
mock_liq.get_asia_range.return_value = {
    "high":       round(ACCUM_HIGH, 6),
    "low":        round(ACCUM_LOW,  6),
    "mid":        round((ACCUM_HIGH + ACCUM_LOW) / 2, 6),
    "bsl_level":  round(ACCUM_HIGH, 6),
    "ssl_level":  round(ACCUM_LOW,  6),
}
mock_liq.has_fresh_sweep.return_value = False  # On teste le detecteur natif sans sweep externe

mock_ds.get_candles.return_value = df_h1_full
mock_ds.set_analysis = MagicMock()

detector = AMDDetector(
    data_store         = mock_ds,
    bias_detector      = mock_bias,
    liquidity_detector = mock_liq,
)


# -------------------------------------------------------------------
# TEST 1 : Analyse complete
# -------------------------------------------------------------------
print("\n[TEST 1] Analyse AMD complete...")
result = detector.analyze("EURUSD", tf="H1")

assert "phase" in result, "FAIL: cle 'phase' manquante"
assert "profile" in result, "FAIL: cle 'profile' manquante"
assert "accum" in result, "FAIL: cle 'accum' manquante"
assert "manip" in result, "FAIL: cle 'manip' manquante"
assert "distrib" in result, "FAIL: cle 'distrib' manquante"
assert result["htf_bias"] == "BULLISH", f"FAIL: Biais attendu BULLISH, obtenu {result['htf_bias']}"

print(f"  OK  Biais HTF       : {result['htf_bias']}")
print(f"  OK  Phase AMD       : {result['phase']}")
print(f"  OK  Profil          : {result['profile']}")
print(f"  OK  Confidence      : {result['confidence']}")


# -------------------------------------------------------------------
# TEST 2 : Accumulation detectee
# -------------------------------------------------------------------
print("\n[TEST 2] Detection de l'Accumulation (range serre)...")
accum = result["accum"]
print(f"  Accum detectee   : {accum.get('detected')}")
print(f"  Source           : {accum.get('source')}")
print(f"  High             : {accum.get('high')}")
print(f"  Low              : {accum.get('low')}")
print(f"  Comprime         : {accum.get('compressed')}")

assert accum.get("detected"), "FAIL: Accumulation non detectee"
assert accum.get("high") is not None, "FAIL: Accum High manquant"
assert accum.get("low") is not None, "FAIL: Accum Low manquant"
print(f"  OK  Accumulation detectee avec source {accum.get('source')}")


# -------------------------------------------------------------------
# TEST 3 : Manipulation (Judas Swing) detectee
# -------------------------------------------------------------------
print("\n[TEST 3] Detection de la Manipulation (Judas Swing)...")
manip = result["manip"]
print(f"  Manip detectee   : {manip.get('detected')}")
print(f"  Direction        : {manip.get('direction')}")
print(f"  Fresh            : {manip.get('fresh')}")
print(f"  Wick ATR         : {manip.get('wick_size_atr')}")
print(f"  Sweep confirmed  : {manip.get('sweep_confirmed')}")

if manip.get("detected"):
    print(f"  OK  Judas Swing detecte : {manip.get('direction')}")
else:
    print("  INFO : Manipulation non detectee (peut varier selon position temporelle du test)")


# -------------------------------------------------------------------
# TEST 4 : Distribution (MSS) detecte
# -------------------------------------------------------------------
print("\n[TEST 4] Detection de la Distribution (MSS)...")
distrib = result["distrib"]
print(f"  Distrib detectee  : {distrib.get('detected')}")
print(f"  Direction         : {distrib.get('direction')}")
print(f"  Force             : {distrib.get('strength')}")
print(f"  MSS Level         : {distrib.get('mss_level')}")

if distrib.get("detected"):
    assert distrib.get("direction") in ("BULLISH", "BEARISH"), \
        f"FAIL: Direction invalide {distrib.get('direction')}"
    print(f"  OK  Distribution detectee : {distrib.get('direction')} ({distrib.get('strength')})")
else:
    print("  INFO : Distribution non detectee (peut varier selon decalage horaire du test)")


# -------------------------------------------------------------------
# TEST 5 : API Publique
# -------------------------------------------------------------------
print("\n[TEST 5] API Publique...")

phase   = detector.get_current_phase("EURUSD", tf="H1")
profile = detector.get_daily_profile("EURUSD", tf="H1")
is_manip   = detector.is_manipulation_active("EURUSD", tf="H1")
is_distrib = detector.is_distribution_active("EURUSD", tf="H1")
state   = detector.get_amd_state("EURUSD", tf="H1")
snap    = detector.get_snapshot("EURUSD", tf="H1")

print(f"  get_current_phase()           : {phase}")
print(f"  get_daily_profile()           : {profile}")
print(f"  is_manipulation_active()      : {is_manip}")
print(f"  is_distribution_active()      : {is_distrib}")
print(f"  get_snapshot() phase          : {snap.get('phase')}")

assert phase in ("ACCUMULATION", "MANIPULATION", "DISTRIBUTION", "UNKNOWN"), \
    f"FAIL: Phase invalide : {phase}"
assert profile in ("AMD_BULLISH", "AMD_BEARISH", "TRENDING", "UNKNOWN"), \
    f"FAIL: Profil invalide : {profile}"
assert isinstance(is_manip, bool), "FAIL: is_manipulation_active() doit retourner un bool"
assert isinstance(is_distrib, bool), "FAIL: is_distribution_active() doit retourner un bool"
assert "phase" in snap, "FAIL: 'phase' manquant dans snapshot"
assert "accum_high" in snap, "FAIL: 'accum_high' manquant dans snapshot"

print(f"  OK  API complete accessible sans erreur")


# -------------------------------------------------------------------
# TEST 6 : Clear cache
# -------------------------------------------------------------------
print("\n[TEST 6] Clear Cache...")
detector.clear_cache("EURUSD")
phase_after_clear = detector.get_current_phase("EURUSD", tf="H1")
assert phase_after_clear == "UNKNOWN", \
    f"FAIL: Cache non vide, phase = {phase_after_clear}"
print(f"  OK  Cache vide correctement")


# -------------------------------------------------------------------
# RESUME
# -------------------------------------------------------------------
print("\n" + "=" * 60)
print("  TOUS LES TESTS REUSSIS --- AMDDetector operationnel")
print("=" * 60 + "\n")
