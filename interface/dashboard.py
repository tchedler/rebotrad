"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Dashboard Plotly 10 Couches ICT
══════════════════════════════════════════════════════════════
Interface Streamlit avec :
- Graphique Plotly 10 couches annotées ICT
- 5 espaces : Monitoring, Analyse ICT, Scalp Output, Stats, Paramètres
- Temps réel via cache market_state_cache.py
══════════════════════════════════════════════════════════════
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import logging

logger = logging.getLogger(__name__)
# Imports des modules du bot
from execution.market_state_cache import MarketStateCache
from analysis.scoring_engine import ScoringEngine
from learning.trade_journal import TradeJournal
from learning.failure_lab import FailureLab
from learning.performance_memory import PerformanceMemory
from interface.telegram_notifier import TelegramNotifier
from config.settings_manager import SettingsManager
from interface.settings_panel import render_settings_panel
from analysis.llm_narrative import generate_narrative

# Config
CACHE_PATH = "market_state_cache.pkl"
REFRESH_INTERVAL = 5  # secondes

st.set_page_config(
    page_title="Sentinel Pro KB5 Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── État global ──
@st.cache_resource
def init_components():
    """Initialise tous les composants."""
    cache    = MarketStateCache()
    journal  = TradeJournal()
    failure_lab = FailureLab(journal)
    perf_mem = PerformanceMemory()
    settings = SettingsManager()    # <-- gestionnaire de paramètres utilisateur
    # Telegram optionnel
    notifier = None
    try:
        if st.secrets.get("TELEGRAM_TOKEN"):
            notifier = TelegramNotifier(
                st.secrets["TELEGRAM_TOKEN"],
                st.secrets["TELEGRAM_CHAT_ID"]
            )
    except Exception as e:
        logger.warning(f"No secrets.toml or error loading secrets: {e}. Telegram notifier disabled.")
    return cache, journal, failure_lab, perf_mem, notifier, settings

cache, journal, failure_lab, perf_mem, notifier, settings = init_components()

# Paires dynamiques depuis les settings utilisateur
PAIRES = settings.get_active_pairs() or ["EURUSDm", "GBPUSDm", "XAUUSDm", "USTECm"]

# ── Sidebar ──
st.sidebar.title("🔧 Paramètres")
selected_pair = st.sidebar.selectbox("Paire", PAIRES)
mode = st.sidebar.radio("Mode", ["Analyse", "Monitoring", "Stats"])
force_refresh = st.sidebar.button("🔄 Refresh forcé")

st.sidebar.markdown("---")

# Récap settings dans la sidebar
rc = settings.get_risk_config()
current_profile = settings.get("profile", "Custom")
st.sidebar.markdown(f"**Profil : `{current_profile}`**")
st.sidebar.markdown(
    f"RR min: **{rc['rr_min']}x** | DD/j: **{rc['max_dd_day_pct']}%**\n\n"
    f"Trades/j max: **{rc['max_trades_day']}** | Risque/trade: **{rc['risk_per_trade']}%**"
)

st.sidebar.info(f"Paires actives : {len(PAIRES)}")

st.sidebar.markdown("---")
# --- Bot Controls ---
st.sidebar.markdown("### 🎛️ Contrôle du Bot")
bot_status = cache.get("bot_status", "Arrêté")
if bot_status == "Actif":
    st.sidebar.success("🟢 BOT ACTIF")
    if st.sidebar.button("🟥 STOPPER LE BOT", use_container_width=True):
        cache.set("bot_status", "Arrêté")
        st.rerun()
else:
    st.sidebar.error("🔴 BOT ARRÊTÉ")
    if st.sidebar.button("🟩 DÉMARRER LE BOT", use_container_width=True):
        cache.set("bot_status", "Actif")
        st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("⚙️ Ouvrir les Paramètres", use_container_width=True):
    st.query_params["tab"] = "settings"
    st.rerun()

# ── Header ──
st.title("📈 Sentinel Pro KB5 — Dashboard ICT")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Score", "93/100", "↑ +12")
with col2:
    st.metric("Trades", journal.get_stats()["total"], "↑ +3")
with col3:
    st.metric("Winrate", f"{journal.get_stats().get('winrate', 0):.1f}%")

# ── Topbar (Active Positions) ──
st.markdown("### ⚔️ Positions Ouvertes Actives")
open_positions = cache.get("open_positions", [])
if not open_positions:
    st.info("ℹ️ Zéro trade en cours sur MT5.")
else:
    for pos in open_positions:
        # Example format: {"ticket": 123, "symbol": "EURUSD", "type": "BUY", "entry": 1.10, "sl": 1.09, "tp": 1.12, "pnl": 50.5}
        color = "green" if pos.get("pnl", 0) > 0 else "red"
        st.markdown(
            f"**{pos.get('symbol', '?')} ({pos.get('type', '?')})** — "
            f"Entrée: {pos.get('entry', '?')} | PnL: <span style='color:{color} font-weight:bold;'>${pos.get('pnl', 0):.2f}</span>",
            unsafe_allow_html=True
        )

st.markdown("---")

# ── Onglets principaux ──
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Analyse ICT", "⚡ Scalp Output", "📚 Stats", "🔧 Contrôles", "⚙️ Paramètres"]
)

# ── TAB 1 : Analyse ICT + Graphique 10 couches ──
with tab1:
    st.header(f"🎯 Analyse {selected_pair}")
    
    # Rafraîchir le cache si bouton
    if force_refresh:
        st.rerun()
    
    # Charger état pour la paire
    state = cache.get(selected_pair, {})
    if not state:
        st.warning("📡 Attente de données...")
    else:
        kb5_result = state.get("kb5_result", {})
        scoring_output = state.get("scoring_output", {})

        # ── SUPER-RADAR MATRICE (Tab 1) ──
        st.markdown("### 📡 Radar ICT Multi-Temporel")
        
        pyramid = kb5_result.get("pyramid_scores", {})
        confluences = kb5_result.get("confluences", [])
        
        # Mots clés detecteurs
        has_mss = "MSS" in " ".join(confluences).upper()
        has_choch = "CHOCH" in " ".join(confluences).upper()
        
        radar_data = []
        for tf in ["MN", "W1", "D1", "H4", "H1", "M15", "M5", "M1"]:
            score = pyramid.get(tf, 0)
            
            status = "En attente"
            if score >= 80: status = "🔥 Exécution A+"
            elif score >= 65: status = "🎯 Tireur d'élite"
            elif score > 0: status = "⏳ Regarder"
            
            radar_data.append({
                "TF": tf,
                "Score": f"{score}/100" if score > 0 else "---",
                "Statut": status,
                "MSS": "✅" if has_mss and score > 60 else "---",
                "CHoCH": "✅" if has_choch and score > 50 else "---",
                "Validé": "🟢" if score >= 65 else "🔴" if score > 0 else "⚫"
            })
            
        st.dataframe(
            pd.DataFrame(radar_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "TF": st.column_config.TextColumn("Unité de Temps", width="small"),
                "Score": st.column_config.TextColumn("Verdict ICT"),
                "Statut": st.column_config.TextColumn("Statut Opérationnel"),
            }
        )

        st.markdown("---")
        
        # Fallback metrics
        st.markdown("### 📊 Métriques Globales")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Score final", scoring_output.get("score", 0))
        with col_m2:
            st.metric("Verdict", scoring_output.get("verdict", "UNKNOWN"))
        with col_m3:
            st.metric("Grade", scoring_output.get("grade", "?"))
        with col_m4:
            st.metric("Direction", scoring_output.get("direction", "NEUTRAL"))

        # ── NARRATIF IA EXPERT ──
        st.markdown("---")
        st.markdown("### 🧠 Narratif Expert IA")
        col_btn, _ = st.columns([1, 3])
        with col_btn:
            if st.button("✨ Générer l'Analyse IA", use_container_width=True):
                st.session_state[f"ai_narrative_{selected_pair}"] = "GENERATING"
                
        # Affichage du narratif
        narrative_key = f"ai_narrative_{selected_pair}"
        if narrative_key in st.session_state:
            if st.session_state[narrative_key] == "GENERATING":
                with st.spinner("Analyse approfondie en cours par l'IA..."):
                    llm_conf = settings.get_llm_config()
                    narrative = generate_narrative(
                        llm_provider=llm_conf["llm_provider"],
                        api_key=llm_conf["llm_api_key"],
                        pair=selected_pair,
                        kb5_result=kb5_result,
                        scoring_output=scoring_output
                    )
                    st.session_state[narrative_key] = narrative
                st.rerun()
            else:
                st.info(st.session_state[narrative_key], icon="🤖")

        st.markdown("---")

        # Graphique 10 couches ICT
        st.subheader("📊 Graphique ICT 10 couches")
        fig = make_subplots(
            rows=1, cols=1,
            subplot_titles=["Analyse ICT Multi-TF"],
            specs=[[{"secondary_y": False}]],
            vertical_spacing=0.1
        )

        # Données OHLCV (dernier TF disponible)
        candles = state.get("candles", [])
        if candles:
            df = pd.DataFrame(candles)
            fig.add_candle(
                x=df["time"], open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                name="Prix", line=dict(width=1), increasing_line_color="green",
                decreasing_line_color="red"
            )

        # Couche 1 : Sessions (rectangles)
        sessions = kb5_result.get("sessions", [])
        for s in sessions:
            fig.add_hrect(
                y0=s["low"], y1=s["high"], x0=s["start"], x1=s["end"],
                fillcolor="rgba(0,100,255,0.1)", line_width=0,
                annotation_text=s["name"], annotation_position="top left"
            )

        # Couche 2 : FVG (rectangles)
        fvgs = kb5_result.get("fvgs", [])
        for fvg in fvgs:
            color = "lightgreen" if fvg["direction"] == "BULLISH" else "lightcoral"
            fig.add_hrect(
                y0=fvg["low"], y1=fvg["high"], x0=fvg["start"], x1=fvg["end"],
                fillcolor=color, line_width=1, line_color="darkgreen" if color=="lightgreen" else "darkred",
                annotation_text=f"FVG {fvg['quality']}"
            )

        # Couche 3 : Order Blocks
        obs = kb5_result.get("order_blocks", [])
        for ob in obs:
            color = "orange" if ob["status"] == "VALID" else "gray"
            fig.add_hrect(
                y0=ob["low"], y1=ob["high"], x0=ob["start"], x1=ob["end"],
                fillcolor=color, opacity=0.7, line_width=2,
                annotation_text=f"OB {ob['quality']}"
            )

        # Couche 4 : Liquidité (lignes)
        liquidity = kb5_result.get("liquidity", {})
        for level, data in liquidity.items():
            fig.add_hline(
                y=data["price"], line_dash="dash", line_color="blue",
                annotation_text=f"{level}: {data['price']}"
            )

        # Couche 5 : DOL cible
        dol = kb5_result.get("dol", {})
        if dol:
            fig.add_vline(
                x=dol["target_time"], line_dash="dot", line_color="purple",
                annotation_text=f"DOL {dol['direction']}"
            )

        # Mise en forme finale
        fig.update_layout(
            title=f"Sentinel Pro KB5 — {selected_pair} (Score: {scoring_output.get('score', 0)})",
            xaxis_title="Temps", yaxis_title="Prix",
            height=600, showlegend=False,
            hovermode="x unified"
        )

        st.plotly_chart(fig, use_container_width=True)

        # Confluences
        st.subheader("🎯 Confluences actives")
        confluences = kb5_result.get("confluences", [])
        for conf in confluences[:10]:
            st.success(f"✅ {conf['name']} (+{conf['score']} pts)")

        if not confluences:
            st.info("Aucune confluence majeure détectée")

# ── TAB 2 : Scalp Output ──
with tab2:
    st.header("⚡ Derniers Scalp Outputs")
    outputs = cache.get("recent_outputs", [])
    for output in outputs:
        with st.expander(f"{output['pair']} — {output['verdict']} {output['score']}/100"):
            st.json(output)

# ── TAB 3 : Stats ──
with tab3:
    st.header("📚 Statistiques")
    
    col1, col2 = st.columns(2)
    with col1:
        stats = journal.get_stats()
        st.metric("Total trades", stats["total"])
        st.metric("Winrate", f"{stats['winrate']:.1f}%")
        st.metric("Erreurs évitables", stats["errors"].get("UNKNOWN", 0))
    
    with col2:
        regret_rate = failure_lab.get_regret_rate()
        st.metric("Regret Rate", f"{regret_rate:.1%}")
        snapshot = perf_mem.get_snapshot()
        st.metric("Malus actifs", snapshot["malus_count"])
    
    # Top erreurs
    st.subheader("Top erreurs récentes")
    errors = journal.get_stats()["errors"]
    df_errors = pd.DataFrame([
        {"Erreur": k, "Count": v} for k, v in errors.items()
    ]).sort_values("Count", ascending=False)
    st.bar_chart(df_errors.set_index("Erreur"))

# ── TAB 4 : Contrôles ──
with tab4:
    st.header("🔧 Contrôles avancés")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 Vider cache"):
            cache.clear()
            st.success("Cache vidé !")
            st.rerun()
        
        if st.button("📊 Autopsie quotidienne"):
            report = failure_lab.run_daily_autopsy()
            st.json(report)
    
    with col2:
        if notifier and st.button("📱 Test Telegram"):
            notifier.send_execute({
                "pair": "EURUSD", "score": 85, "verdict": "EXECUTE"
            })
            st.success("Test Telegram envoyé !")
        
        if st.button("🔄 Reset Performance Memory"):
            perf_mem.reset()
            st.success("Mémoire performance reset !")

# ── TAB 5 : Paramètres Avancés ──
with tab5:
    render_settings_panel(settings)

# ── Footer temps réel ──
st.markdown("---")
col_f1, col_f2 = st.columns([1, 1])
with col_f1:
    st.caption(f"🕐 Dernière mise à jour : {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
with col_f2:
    auto_refresh = st.toggle("🔄 Auto-refresh (5s)", value=False, help="Désactivez pendant le paramétrage pour éviter les crashs d'interface.")

if auto_refresh:
    time.sleep(REFRESH_INTERVAL)
    st.rerun()

