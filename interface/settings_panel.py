# interface/settings_panel.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Panneau de Paramètres (Streamlit)
══════════════════════════════════════════════════════════════
Panneau complet de configuration intégré dans le Dashboard.

Sections :
  1. Profils préconçus (ICT Pur, SMC+ICT, Conservateur, Agressif, Custom)
  2. Sélection des paires actives (multi-select par catégorie)
  3. Écoles de trading → activer/désactiver
  4. Principes par école (toggle individuel)
  5. Paramètres de Risque (RR, DD, trades/jour, % par trade)
  6. Filtres globaux (Killzone, ERL, MSS, etc.)
  7. Scoring (seuils EXECUTE / WATCH)

Intégration : appelé depuis dashboard.py dans l'onglet ⚙️ Paramètres
══════════════════════════════════════════════════════════════
"""

import streamlit as st
from config.settings_manager import (
    SettingsManager,
    SCHOOLS,
    PROFILES,
    AVAILABLE_PAIRS,
)


def render_settings_panel(settings: SettingsManager) -> None:
    """
    Rend l'intégralité du panneau de paramètres.

    Args:
        settings: instance SettingsManager (partagée avec le reste de l'app)
    """
    st.markdown("## ⚙️ Paramètres Avancés — Sentinel Pro KB5")
    st.markdown(
        "Configurez ici le comportement exact du bot : quels marchés analyser, "
        "quelles règles ICT appliquer, et comment gérer le risque."
    )
    st.markdown("---")

    # ══════════════════════════════════════════════════
    # SECTION 0 — PROFILS PRÉCONÇUS
    # ══════════════════════════════════════════════════
    _render_profiles(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 1 — SÉLECTION DES PAIRES
    # ══════════════════════════════════════════════════
    _render_pairs(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 2 — ÉCOLES + PRINCIPES
    # ══════════════════════════════════════════════════
    _render_schools_and_principles(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 3 — RISQUE
    # ══════════════════════════════════════════════════
    _render_risk(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 4 — SCORING
    # ══════════════════════════════════════════════════
    _render_scoring(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 5 — FILTRES GLOBAUX
    # ══════════════════════════════════════════════════
    _render_global_filters(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # SECTION 6 — IA (NARRATIF LLM)
    # ══════════════════════════════════════════════════
    _render_ai_config(settings)

    st.markdown("---")
    # ══════════════════════════════════════════════════
    # RESET
    # ══════════════════════════════════════════════════
    st.markdown("### 🗑️ Réinitialisation")
    col_r1, col_r2 = st.columns([1, 3])
    with col_r1:
        if st.button("⚠️ Réinitialiser tout", type="secondary", key="btn_reset_all"):
            settings.reset_to_defaults()
            st.success("✅ Paramètres réinitialisés aux valeurs par défaut.")
            st.rerun()
    with col_r2:
        last = settings.get("last_updated")
        if last:
            st.caption(f"Dernière sauvegarde : {last[:19].replace('T', ' ')} UTC")


# ══════════════════════════════════════════════════════════════
# _render_profiles
# ══════════════════════════════════════════════════════════════

def _render_profiles(settings: SettingsManager) -> None:
    """Section profils préconçus."""
    st.markdown("### 🎯 Profils de Trading")
    st.caption(
        "Chaque profil précharge une configuration complète. "
        "Vous pouvez ensuite affiner chaque paramètre manuellement."
    )

    current_profile = settings.get("profile", "Custom")
    profile_names   = list(PROFILES.keys())

    # Cartes de profils
    cols = st.columns(len(profile_names))
    for i, pname in enumerate(profile_names):
        with cols[i]:
            pdata   = PROFILES[pname]
            is_active = (pname == current_profile)
            style   = "border: 2px solid #00d4ff;" if is_active else "border: 1px solid #444;"
            st.markdown(
                f"""<div style="{style} border-radius:8px; padding:10px; margin-bottom:8px; background:#0f1117;">
                <b style="color:{'#00d4ff' if is_active else '#fff'};">{pname}</b><br>
                <small style="color:#aaa;">{pdata['description']}</small><br>
                <small>RR min: {pdata['rr_min']}x | DD/j: {pdata['max_dd_day_pct']}%</small>
                </div>""",
                unsafe_allow_html=True,
            )
            if not is_active:
                if st.button(f"Appliquer", key=f"btn_profile_{pname}", use_container_width=True):
                    settings.apply_profile(pname)
                    st.success(f"✅ Profil {pname} appliqué.")
                    st.rerun()
            else:
                st.success("✅ Actif")


# ══════════════════════════════════════════════════════════════
# _render_pairs
# ══════════════════════════════════════════════════════════════

def _render_pairs(settings: SettingsManager) -> None:
    """Section sélection des paires."""
    st.markdown("### 📈 Paires de Trading Actives")
    st.caption(
        "Choisissez les paires que le bot va analyser et trader. "
        "Limitez-vous à 6-8 paires max pour des performances optimales."
    )

    current_pairs = settings.get_active_pairs()
    all_selected  = []

    for category, pairs in AVAILABLE_PAIRS.items():
        with st.expander(f"📂 {category} ({len(pairs)} paires)", expanded=(category == "Forex Majeurs m")):
            # Rendu simple (sans colonnes dynamiques pour éviter le bug React)
            for pair in pairs:
                checked = st.checkbox(
                    pair,
                    value=(pair in current_pairs),
                    key=f"pair_{pair}"
                )
                if checked:
                    all_selected.append(pair)

    # Affichage résumé + bouton sauvegarder
    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        if all_selected:
            st.info(f"**{len(all_selected)} paires sélectionnées :** {', '.join(all_selected)}")
        else:
            st.warning("⚠️ Aucune paire sélectionnée — le bot ne peut pas fonctionner.")
    with col_s2:
        if st.button("💾 Sauvegarder les paires", key="btn_save_pairs", use_container_width=True):
            settings.set_active_pairs(all_selected)
            st.success("✅ Paires sauvegardées !")


# ══════════════════════════════════════════════════════════════
# _render_schools_and_principles
# ══════════════════════════════════════════════════════════════

def _render_schools_and_principles(settings: SettingsManager) -> None:
    """Section écoles de trading et leurs principes."""
    st.markdown("### 🏫 Écoles de Trading & Principes")
    st.caption(
        "Activez les écoles et ajustez chaque principe individuellement. "
        "Un principe désactivé est ignoré dans le scoring et les filtres."
    )

    schools_enabled = list(settings.get("schools_enabled", []))
    principles_enabled = dict(settings.get("principles_enabled", {}))
    changed = False

    for school_id, school_data in SCHOOLS.items():
        school_active = school_id in schools_enabled
        color         = school_data["color"]

        # En-tête école avec toggle
        col_h1, col_h2 = st.columns([4, 1])
        with col_h1:
            st.markdown(
                f"<h4 style='color:{color}; margin-bottom:4px;'>"
                f"{'🟢' if school_active else '⚫'} {school_data['name']}</h4>"
                f"<small style='color:#888;'>{school_data['description']}</small>",
                unsafe_allow_html=True,
            )
        with col_h2:
            new_school_active = st.toggle(
                "Actif",
                value=school_active,
                key=f"school_toggle_{school_id}",
            )
            if new_school_active != school_active:
                if new_school_active and school_id not in schools_enabled:
                    schools_enabled.append(school_id)
                elif not new_school_active and school_id in schools_enabled:
                    schools_enabled.remove(school_id)
                changed = True

        # Principes de l'école
        if new_school_active:
            with st.expander(
                f"🔧 Configurer les {len(school_data['principles'])} principes {school_data['name']}",
                expanded=False,
            ):
                principles = school_data["principles"]
                # Rendu simple vertical pour éviter le bug DOM React de Streamlit
                for pid, pdata in principles.items():
                    full_key = f"{school_id}:{pid}"
                    current_val = principles_enabled.get(full_key, pdata["default"])
                    new_val = st.checkbox(
                        f"**{pdata['label']}** — {pdata['desc']}",
                        value=current_val,
                        key=f"principle_{school_id}_{pid}",
                    )
                    if new_val != current_val:
                        principles_enabled[full_key] = new_val
                        changed = True
        else:
            st.caption("*École désactivée — tous les principes ignorés.*")

        st.markdown("&nbsp;")

    # Bouton sauvegarder les écoles et principes
    if st.button("💾 Sauvegarder les écoles & principes", key="btn_save_schools"):
        settings.update_bulk({
            "schools_enabled":   schools_enabled,
            "principles_enabled": principles_enabled,
            "profile":           "Custom",
        })
        st.success("✅ Configuration sauvegardée ! Le profil a été mis en mode Custom.")
        st.rerun()
    elif changed:
        st.info("ℹ️ Des changements sont en attente — cliquez sur Sauvegarder.")


# ══════════════════════════════════════════════════════════════
# _render_risk
# ══════════════════════════════════════════════════════════════

def _render_risk(settings: SettingsManager) -> None:
    """Section paramètres de risque."""
    st.markdown("### 💰 Gestion du Risque")
    st.caption("Ces paramètres définissent le cadre de risque dans lequel le bot opère.")

    rc = settings.get_risk_config()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**📊 Taille de Position**")
        risk_per_trade = st.slider(
            "Risque par trade (% du capital)",
            min_value=0.1, max_value=5.0, step=0.1,
            value=float(rc["risk_per_trade"]),
            key="risk_per_trade_slider",
            help="% de votre capital que vous risquez sur chaque trade"
        )
        use_partial_tp = st.checkbox(
            "TP Partiel via IRL",
            value=rc["use_partial_tp"],
            key="use_partial_tp_cb",
            help="Fermer 50% à TP1 (IRL), le reste vers cible finale (ERL)"
        )

    with col2:
        st.markdown("**⏱️ Limites Journalières**")
        max_trades_day = st.number_input(
            "Nombre max de trades / jour",
            min_value=1, max_value=30,
            value=int(rc["max_trades_day"]),
            key="max_trades_day_input",
            help="Au-delà de cette limite, le bot s'arrête pour la journée"
        )
        max_dd_day = st.slider(
            "Drawdown max / jour (%)",
            min_value=0.5, max_value=10.0, step=0.5,
            value=float(rc["max_dd_day_pct"]),
            key="max_dd_day_slider",
            help="Si la perte journalière dépasse ce seuil, arrêt du bot"
        )
        max_dd_week = st.slider(
            "Drawdown max / semaine (%)",
            min_value=1.0, max_value=20.0, step=0.5,
            value=float(rc["max_dd_week_pct"]),
            key="max_dd_week_slider",
            help="Drawdown hebdomadaire max avant arrêt total (KS1)"
        )

    with col3:
        st.markdown("**🎯 Risk / Reward**")
        rr_min = st.slider(
            "RR minimum accepté",
            min_value=0.5, max_value=10.0, step=0.5,
            value=float(rc["rr_min"]),
            key="rr_min_slider",
            help="En dessous de ce RR, le trade est rejeté automatiquement"
        )
        rr_target = st.slider(
            "RR cible (TP1 → TP2)",
            min_value=0.5, max_value=15.0, step=0.5,
            value=float(rc["rr_target"]),
            key="rr_target_slider",
            help="Le bot cherche d'abord ce RR comme objectif optimal"
        )

        # Affichage visuel RR
        rr_color = "#10b981" if rr_min >= 2.0 else ("#f59e0b" if rr_min >= 1.5 else "#ef4444")
        st.markdown(
            f"<div style='background:{rr_color}22; border-left:3px solid {rr_color}; "
            f"padding:8px; border-radius:4px; margin-top:8px;'>"
            f"RR min actuel : <b style='color:{rr_color};'>{rr_min:.1f}x</b>"
            f" | Cible : <b style='color:{rr_color};'>{rr_target:.1f}x</b></div>",
            unsafe_allow_html=True,
        )

    # Bouton sauvegarde risque
    if st.button("💾 Sauvegarder le Risque", key="btn_save_risk", type="primary"):
        settings.update_bulk({
            "risk_per_trade":  risk_per_trade,
            "max_trades_day":  max_trades_day,
            "max_dd_day_pct":  max_dd_day,
            "max_dd_week_pct": max_dd_week,
            "rr_min":          rr_min,
            "rr_target":       rr_target,
            "use_partial_tp":  use_partial_tp,
            "profile":         "Custom",
        })
        st.success("✅ Paramètres de risque sauvegardés !")


# ══════════════════════════════════════════════════════════════
# _render_scoring
# ══════════════════════════════════════════════════════════════

def _render_scoring(settings: SettingsManager) -> None:
    """Section seuils de scoring."""
    st.markdown("### 🏆 Seuils de Scoring")
    st.caption(
        "Le bot calcule un score ICT de 0 à 100 pour chaque setup. "
        "Ces seuils définissent à partir de quand il agit."
    )

    rc = settings.get_risk_config()

    col1, col2 = st.columns(2)
    with col1:
        score_execute = st.slider(
            "Score EXECUTE (trader le setup)",
            min_value=50, max_value=100,
            value=int(rc["score_execute"]),
            key="score_execute_slider",
            help="Le bot exécute uniquement si le score >= ce seuil"
        )
    with col2:
        score_watch = st.slider(
            "Score WATCH (surveiller sans trader)",
            min_value=40, max_value=95,
            value=int(rc["score_watch"]),
            key="score_watch_slider",
            help="Le bot met en surveillance si le score >= ce seuil"
        )

    # Visualisation de la zone de scoring
    st.markdown(
        f"""<div style="background:#0f1117; border:1px solid #333; border-radius:8px; padding:12px; margin-top:8px;">
        <div style="display:flex; align-items:stretch; height:30px; border-radius:4px; overflow:hidden;">
          <div style="flex:{score_watch}; background:#ef444433; display:flex; align-items:center; justify-content:center;">
            <span style="font-size:11px; color:#ef4444;">NO TRADE (&lt;{score_watch})</span>
          </div>
          <div style="flex:{score_execute - score_watch}; background:#f59e0b33; display:flex; align-items:center; justify-content:center;">
            <span style="font-size:11px; color:#f59e0b;">WATCH ({score_watch}–{score_execute})</span>
          </div>
          <div style="flex:{100 - score_execute}; background:#10b98133; display:flex; align-items:center; justify-content:center;">
            <span style="font-size:11px; color:#10b981;">EXECUTE (&geq;{score_execute})</span>
          </div>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    if score_watch >= score_execute:
        st.error("⚠️ Le seuil WATCH doit être inférieur au seuil EXECUTE.")
    else:
        if st.button("💾 Sauvegarder le Scoring", key="btn_save_scoring"):
            settings.update_bulk({
                "score_execute": score_execute,
                "score_watch":   score_watch,
                "profile":       "Custom",
            })
            st.success("✅ Seuils de scoring sauvegardés !")


# ══════════════════════════════════════════════════════════════
# _render_global_filters
# ══════════════════════════════════════════════════════════════

def _render_global_filters(settings: SettingsManager) -> None:
    """Section filtres globaux."""
    st.markdown("### 🔒 Filtres Globaux (Conditions d'Entrée)")
    st.caption(
        "Ces filtres s'appliquent à chaque setup AVANT le scoring. "
        "Si la condition n'est pas remplie, le trade est refusé."
    )

    rc = settings.get_risk_config()

    col1, col2 = st.columns(2)
    with col1:
        require_killzone = st.checkbox(
            "🕐 Killzone ICT obligatoire",
            value=rc["require_killzone"],
            key="require_killzone_cb",
            help="Refuser tous les trades en dehors d'une Killzone (Londres / NY / Asie)"
        )
        require_erl = st.checkbox(
            "💧 ERL sweepé obligatoire",
            value=rc["require_erl"],
            key="require_erl_cb",
            help="Le bot ne trade que si une prise de liquidité externe a eu lieu"
        )
        require_mss = st.checkbox(
            "📐 MSS confirmé obligatoire",
            value=rc["require_mss"],
            key="require_mss_cb",
            help="Exiger un Market Structure Shift frais dans la direction du trade"
        )
    with col2:
        require_choch = st.checkbox(
            "⚡ CHoCH confirmé obligatoire",
            value=rc["require_choch"],
            key="require_choch_cb",
            help="Exiger un Change of Character LTF avant d'entrer"
        )

    st.markdown("**Résumé des filtres actifs :**")
    active_filters = []
    if require_killzone: active_filters.append("Killzone")
    if require_erl:      active_filters.append("ERL Sweep")
    if require_mss:      active_filters.append("MSS")
    if require_choch:    active_filters.append("CHoCH")

    if active_filters:
        tags = " • ".join([f"`{f}`" for f in active_filters])
        st.markdown(f"✅ Filtres obligatoires : {tags}")
    else:
        st.warning("⚠️ Aucun filtre obligatoire — le bot peut entrer sur n'importe quel signal.")

    if st.button("💾 Sauvegarder les Filtres", key="btn_save_filters"):
        settings.update_bulk({
            "require_killzone": require_killzone,
            "require_erl":      require_erl,
            "require_mss":      require_mss,
            "require_choch":    require_choch,
            "profile":          "Custom",
        })
        st.success("✅ Filtres globaux sauvegardés !")

# ══════════════════════════════════════════════════════════════
# _render_ai_config
# ══════════════════════════════════════════════════════════════

def _render_ai_config(settings: SettingsManager) -> None:
    """Section configuration de l'intelligence artificielle pour le narratif."""
    st.markdown("### 🧠 Configuration IA (Génération du Narratif)")
    st.caption(
        "Sélectionnez le modèle LLM et entrez votre clé API pour permettre au "
        "dashboard de générer un bulletin d'analyse écrit au format institutionnel."
    )

    llm_conf = settings.get_llm_config()

    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "🗣️ Fournisseur IA",
            options=["Gemini", "Grok", "OpenAI", "Claude"],
            index=["Gemini", "Grok", "OpenAI", "Claude"].index(llm_conf["llm_provider"]) if llm_conf["llm_provider"] in ["Gemini", "Grok", "OpenAI", "Claude"] else 0,
            key="llm_provider_sb"
        )
    with col2:
        api_key = st.text_input(
            "🔑 Clé API",
            value=llm_conf["llm_api_key"],
            type="password",
            key="llm_api_key_in",
            help="Votre clé restera chiffrée localement."
        )

    if st.button("💾 Sauvegarder Config IA", key="btn_save_ai"):
        settings.update_bulk({
            "llm_provider": provider,
            "llm_api_key":  api_key,
        })
        st.success(f"✅ Configuration IA ({provider}) sauvegardée !")
