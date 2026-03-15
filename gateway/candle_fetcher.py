# gateway/candle_fetcher.py
# Sentinel Pro KB5 — Récupération Bougies MT5
#
# Responsabilités :
# - Fetch bougies historiques par paire/TF
# - DataFrame propre OHLCV + spread + realvolume
# - Activation automatique des symboles (symbolselect)
# - Fetch depuis une date (post-reconnexion, sans recharger tout)
# - Dernière bougie fermée → Analyse KB5
# - Bougie en cours → Anomaly Detector
# - Fetch tous TF en une passe
# - get_pip_value() pour Capital Allocator
# - get_symbol_info() pour taille de position

import MetaTrader5 as mt5
import pandas as pd
import logging
from datetime import datetime, timezone
from config.constants import TIMEFRAMES, CANDLES_PER_TF

logger = logging.getLogger(__name__)


class CandleFetcher:
    """
    Fournit des DataFrames OHLCV propres depuis MT5.

    Colonnes garanties : open, high, low, close, volume, real_volume, spread
    Index               : datetime UTC timezone-aware

    Règles :
    - Ne jamais utiliser iloc[-1] pour l'analyse → bougie non fermée
    - Toujours iloc[-2] pour la dernière bougie FERMÉE
    - iloc[-1] réservé à l'Anomaly Detector uniquement
    """

    # ─────────────────────────────────────────────
    # ACTIVATION SYMBOLE
    # ─────────────────────────────────────────────

    def _ensure_symbol_active(self, pair: str) -> bool:
        """
        Active la paire dans MT5 si elle ne l'est pas.

        CRITIQUE : sans ça, copy_rates_from_pos() retourne None
        silencieusement même si la paire existe sur le compte.
        Touche ~30% des paires non affichées dans le terminal.
        """
        info = mt5.symbol_info(pair)
        if info is None:
            logger.error(f"Symbole inconnu sur ce compte : {pair}")
            return False
        if not info.visible:
            if not mt5.symbol_select(pair, True):
                logger.error(
                    f"Impossible d'activer le symbole {pair} : {mt5.last_error()}"
                )
                return False
            logger.debug(f"Symbole {pair} activé dans MT5.")
        return True

    # ─────────────────────────────────────────────
    # FETCH PRINCIPAL
    # ─────────────────────────────────────────────

    def fetch(self, pair: str, timeframe: str) -> pd.DataFrame:
        """
        Charge les N dernières bougies (fermées + en cours).
        N défini par CANDLES_PER_TF dans constants.py.
        Retourne DataFrame vide si erreur.
        """
        tf    = TIMEFRAMES.get(timeframe)
        count = CANDLES_PER_TF.get(timeframe, 300)

        if tf is None:
            logger.error(f"Timeframe inconnu : {timeframe}")
            return pd.DataFrame()

        if not self._ensure_symbol_active(pair):
            return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(pair, tf, 0, count)

        if rates is None or len(rates) == 0:
            logger.warning(
                f"Aucune donnée pour {pair}/{timeframe} "
                f"— Erreur MT5 : {mt5.last_error()}"
            )
            return pd.DataFrame()

        return self._build_dataframe(rates, pair, timeframe)

    # ─────────────────────────────────────────────
    # FETCH DEPUIS UNE DATE (post-reconnexion)
    # ─────────────────────────────────────────────

    def fetch_since(
        self, pair: str, timeframe: str, since: datetime
    ) -> pd.DataFrame:
        """
        Charge uniquement les bougies depuis une date précise.

        Utilisé après reconnexion Gateway pour ne charger
        que les bougies manquantes — pas tout l'historique.

        Args:
            since : datetime UTC (avec ou sans timezone)
        """
        tf = TIMEFRAMES.get(timeframe)
        if tf is None:
            logger.error(f"Timeframe inconnu : {timeframe}")
            return pd.DataFrame()

        if not self._ensure_symbol_active(pair):
            return pd.DataFrame()

        # Garantir UTC timezone-aware
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        rates = mt5.copy_rates_from(
            pair, tf, since, CANDLES_PER_TF.get(timeframe, 300)
        )

        if rates is None or len(rates) == 0:
            logger.debug(
                f"Aucune nouvelle bougie pour {pair}/{timeframe} "
                f"depuis {since}"
            )
            return pd.DataFrame()

        df = self._build_dataframe(rates, pair, timeframe)
        logger.info(
            f"Bougies manquantes {pair}/{timeframe} : "
            f"{len(df)} chargées depuis {since}"
        )
        return df

    # ─────────────────────────────────────────────
    # FETCH TOUS LES TIMEFRAMES
    # ─────────────────────────────────────────────

    def fetch_all_timeframes(self, pair: str) -> dict:
        """
        Charge tous les TF pour une paire en une seule passe.
        Retourne dict {tf_name: DataFrame}.
        TF vides retournés comme DataFrame vide — pas d'exception.
        """
        data   = {}
        failed = []

        for tf_name in TIMEFRAMES.keys():
            df = self.fetch(pair, tf_name)
            data[tf_name] = df
            if df.empty:
                failed.append(tf_name)

        if failed:
            logger.warning(f"{pair} — TF sans données : {failed}")
        else:
            logger.info(f"{pair} — Tous les TF chargés ({len(TIMEFRAMES)}).")

        return data

    # ─────────────────────────────────────────────
    # DERNIÈRE BOUGIE FERMÉE
    # ─────────────────────────────────────────────

    def fetch_latest_closed(self, pair: str, timeframe: str) -> dict:
        """
        Retourne la dernière bougie FERMÉE.
        iloc[-2] car iloc[-1] = bougie en cours (non fermée).

        Utilisé par le Service Analyse pour tous les calculs KB5.
        NE PAS utiliser fetch_current_candle() pour l'analyse.
        """
        df = self.fetch(pair, timeframe)
        if df.empty or len(df) < 2:
            return {}

        candle = df.iloc[-2]
        return {
            "time":        str(df.index[-2]),
            "open":        round(float(candle["open"]),        5),
            "high":        round(float(candle["high"]),        5),
            "low":         round(float(candle["low"]),         5),
            "close":       round(float(candle["close"]),       5),
            "volume":      int(candle["volume"]),
            "real_volume": int(candle["real_volume"]),
            "spread":      int(candle["spread"]),
            "timeframe":   timeframe,
            "pair":        pair,
            "closed":      True,
        }

    # ─────────────────────────────────────────────
    # BOUGIE EN COURS (Anomaly Detector uniquement)
    # ─────────────────────────────────────────────

    def fetch_current_candle(self, pair: str, timeframe: str) -> dict:
        """
        Retourne la bougie EN COURS (non fermée). iloc[-1].

        Utilisé UNIQUEMENT par l'Anomaly Detector pour détecter :
        - Flash crash (bougie > 3x ATR en cours)
        - Spread anormal en temps réel

        ⚠️ NE PAS utiliser pour les calculs d'Analyse KB5.
           Données instables — bougie non fermée.
        """
        df = self.fetch(pair, timeframe)
        if df.empty:
            return {}

        candle = df.iloc[-1]
        return {
            "time":        str(df.index[-1]),
            "open":        round(float(candle["open"]),        5),
            "high":        round(float(candle["high"]),        5),
            "low":         round(float(candle["low"]),         5),
            "close":       round(float(candle["close"]),       5),
            "volume":      int(candle["volume"]),
            "real_volume": int(candle["real_volume"]),
            "spread":      int(candle["spread"]),
            "timeframe":   timeframe,
            "pair":        pair,
            "closed":      False,
            "in_progress": True,
        }

    # ─────────────────────────────────────────────
    # CONSTRUCTION DATAFRAME
    # ─────────────────────────────────────────────

    def _build_dataframe(
        self, rates, pair: str, timeframe: str
    ) -> pd.DataFrame:
        """
        Construit un DataFrame propre depuis les rates MT5.

        Colonnes garanties :
            open, high, low, close, volume, real_volume, spread
        Index :
            datetime UTC timezone-aware

        Corrections vs version initiale :
        - real_volume inclus (volume réel Exness, absent sur certains brokers)
        - spread inclus par bougie (utilisé par KS4)
        - Colonnes manquantes remplies avec 0 (pas d'exception)
        - Index datetime UTC avec timezone
        - Ordre des colonnes fixe
        """
        df = pd.DataFrame(rates)

        # Index datetime UTC timezone-aware
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)

        # Renommage tick_volume → volume
        rename_map = {"tick_volume": "volume"}
        df.rename(columns=rename_map, inplace=True)

        # Colonnes finales — ordre fixe
        cols = ["open", "high", "low", "close", "volume", "real_volume", "spread"]

        # Ajouter colonnes manquantes avec 0
        # (real_volume absent sur certains brokers hors Exness)
        for col in cols:
            if col not in df.columns:
                df[col] = 0

        df = df[cols]

        logger.debug(
            f"{pair}/{timeframe} — {len(df)} bougies "
            f"[{df.index[0]} → {df.index[-1]}]"
        )
        return df

    # ─────────────────────────────────────────────
    # INFORMATIONS SYMBOLE
    # ─────────────────────────────────────────────

    def get_symbol_info(self, pair: str) -> dict:
        """
        Retourne les infos du symbole : digits, point, spread actuel,
        contract_size, volumes min/max/step, devises.

        Utilisé par Capital Allocator pour calculer la taille de position.
        """
        if not self._ensure_symbol_active(pair):
            return {}

        info = mt5.symbol_info(pair)
        if info is None:
            return {}

        return {
            "pair":            pair,
            "digits":          info.digits,
            "point":           info.point,
            "spread":          info.spread,
            "contract_size":   info.trade_contract_size,
            "min_volume":      info.volume_min,
            "max_volume":      info.volume_max,
            "volume_step":     info.volume_step,
            "currency_base":   info.currency_base,
            "currency_profit": info.currency_profit,
        }

    def get_pip_value(self, pair: str) -> float:
        """
        Valeur d'un pip pour cette paire.
        Utilisé par Capital Allocator pour calculer la taille de position exacte.

        FOREX standard : point × 10
        JPY pairs      : point × 100
        XAUUSD/indices : point × 10 (MT5 normalise déjà)
        """
        info = mt5.symbol_info(pair)
        if info is None:
            return 0.0

        if "JPY" in pair:
            return round(info.point * 100, 6)
        return round(info.point * 10, 6)

    def __repr__(self):
        return "CandleFetcher(MT5)"
