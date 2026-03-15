# execution/news_manager.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Gestionnaire de Calendrier Économique
══════════════════════════════════════════════════════════════
Responsabilités :
  - Se connecter à l'API Finnhub (Calendrier Économique)
  - Extraire les news à impact élevé (HIGH)
  - Filtrer par devises majeures (USD, EUR, GBP, JPY, CAD, AUD)
  - Mettre à jour KillSwitchEngine via un cache partagé
  - S'exécuter en arrière-plan toutes les 6 heures

Note : Nécessite une clé API Finnhub (FINNHUB_API_KEY)
══════════════════════════════════════════════════════════════
"""

import logging
import requests
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

class NewsManager:
    """
    Gère la récupération et le filtrage des news économiques.
    Fournit les données filtrées à KillSwitchEngine via un callback.
    """

    def __init__(self, api_key: str = "YOUR_FINNHUB_API_KEY", on_update_callback=None):
        self.api_key = api_key
        self.on_update_callback = on_update_callback
        self._news_cache: List[dict] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # Devises à surveiller
        self.watched_currencies = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"]

    def start(self, interval_hours: int = 6):
        """Démarre le thread de mise à jour automatique."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(interval_hours,),
            name="NewsManagerThread",
            daemon=True
        )
        self._thread.start()
        logger.info(f"NewsManager démarré — Intervalle : {interval_hours}h")

    def stop(self):
        """Arrête le thread NewsManager."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("NewsManager arrêté")

    def get_high_impact_news(self) -> List[dict]:
        """Retourne la liste des news à impact élevé en cache."""
        with self._lock:
            return list(self._news_cache)

    def force_refresh(self):
        """Force une mise à jour immédiate des news."""
        self._update_news()

    def _run_loop(self, interval_hours: int):
        """Boucle de mise à jour périodique."""
        while not self._stop_event.is_set():
            try:
                self._update_news()
            except Exception as e:
                logger.error(f"NewsManager — Erreur lors de la mise à jour : {e}")

            # Attendre l'intervalle ou l'événement d'arrêt
            wait_seconds = interval_hours * 3600
            self._stop_event.wait(timeout=wait_seconds)

    def _update_news(self):
        """Récupère les news via l'API Finnhub."""
        if not self.api_key or "YOUR_FINNHUB" in self.api_key:
            logger.warning("NewsManager — Clé API Finnhub non configurée. Impossible de charger les news.")
            return

        # Fenêtre : d'aujourd'hui à +3 jours
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")

        url = f"https://finnhub.io/api/v1/calendar/economic?from={start_date}&to={end_date}&token={self.api_key}"
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            raw_events = data.get("economicCalendar", [])
            filtered_events = []

            for event in raw_events:
                # 1. Filtre Impact (On ne veut que le High impact)
                impact = event.get("impact", "").upper()
                if impact != "HIGH":
                    continue

                # 2. Filtre Devise
                currency = event.get("country", "").upper()
                # Finnhub utilise souvent le pays (US, GB, etc.) au lieu de la devise (USD, GBP)
                # On mappe les principaux
                country_map = {
                    "UNITED STATES": "USD", "US": "USD",
                    "EURO AREA": "EUR", "EUROPE": "EUR", "GERMANY": "EUR", "FRANCE": "EUR",
                    "UNITED KINGDOM": "GBP", "UK": "GBP",
                    "JAPAN": "JPY", "CANADA": "CAD", "AUSTRALIA": "AUD", "NEW ZEALAND": "NZD",
                    "SWITZERLAND": "CHF"
                }
                
                mapped_currency = country_map.get(currency, currency)
                if mapped_currency not in self.watched_currencies:
                    continue

                # 3. Parsing Date
                # Format Finnhub : "2024-03-12 12:30:00" (UTC)
                date_str = event.get("time", "")
                if not date_str:
                    continue
                
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                filtered_events.append({
                    "time": dt,
                    "currency": mapped_currency,
                    "event": event.get("event", "Economic News"),
                    "impact": impact
                })

            with self._lock:
                self._news_cache = filtered_events
            
            logger.info(f"NewsManager — {len(filtered_events)} news à impact élevé chargées.")

            # Trigger callback
            if self.on_update_callback:
                try:
                    self.on_update_callback(filtered_events)
                except Exception as e:
                    logger.error(f"NewsManager — Erreur dans le callback : {e}")

        except Exception as e:
            logger.error(f"NewsManager — Erreur API Finnhub : {e}")

# singleton
_manager = None
def get_news_manager(api_key: str = None) -> NewsManager:
    global _manager
    if _manager is None:
        _manager = NewsManager(api_key) if api_key else NewsManager()
    return _manager
