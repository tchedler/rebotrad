# Sentinel Pro — Trading Bot KB5

Foundational components of the Sentinel Pro trading bot architecture, based on KB5 specifications.

## Phase 1 — MT5 Gateway & Data Store
- **MT5 Connector**: Stable connection with heartbeat and auto-reconnect.
- **Data Store**: Central thread-safe storage for ticks, candles, and analysis dossiers.
- **Tick Receiver**: Real-time tick reception with Behaviour Shield limits.
- **Candle Fetcher**: Historical data (M1 to MN) fetching.
- **Order Reader**: Open positions and pending orders monitoring.
- **Heartbeat Monitor**: System-wide components health check.
- **Priority Queue**: Killzone-based pair prioritization.

## Installation
1. `pip install -r requirements.txt`
2. `cp .env.example .env` (Set your Exness credentials)
3. `python main.py`
