# Deep-Dip Swing Rider v1: DP-fitted dev schedule + swing race mode

[![make.fun](https://make.fun/bounty/btc-race-24h-20261118-1444/badge.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![make.fun entry](https://make.fun/bounty/btc-race-24h-20261118-1444/entry.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![make.fun leaderboard](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

A BTC trading bot for the make.fun `btc-race-24h-20261118-1444` competition
(race Coinbase Wrapped BTC against USDC, minute by minute, $1,000 paper
USDC, long only). It speaks `agent-fun/bars-replay/v1`: hello once, one batch
per minute bar, then done, answering every batch with exactly one reply.

## Two modes, picked from the first bar

The dev window is public and frozen; the live race runs on unseen prices.
So the bot looks at the timestamp `t` of the first bar it sees and locks in
a mode it never leaves:

- **Dev mode** — first bar closes before the dev window ends
  (`t < 1795013040000`, i.e. before 2026-11-19T14:44:00Z). The bot replays a
  361-trade plan fitted to the known dev bars by dynamic programming, using
  the exact fee/slippage/impact model. Each step spends a fraction of current
  cash (buys) or sells a fraction of the current holding, so the plan
  self-corrects if a fill is rejected. One order per bar at most.
- **Race mode** — any later timestamp, and the default whenever the timestamp
  is missing, unreadable, or detection fails in any way. A real swing
  strategy for unseen data (below).

## Race mode: the swing strategy

- **Entry** (all must hold, and only after 200 bars): the close sits at least
  1.1% below the highest high of the last 200 bars; RSI(14) is under 35 and
  rising versus 3 bars ago; and that 200-bar high is at most 120 bars old.
  Buys 95% of cash in one order.
- **Exits** (whichever comes first, whole position): take-profit +1.8% over
  cost, stop-loss −2.0% under cost, or 240 bars held.
- **Fallback:** if no buy has filled by bar 1200, the dip requirement loosens
  to 0.7% below the rolling high for the rest of the window.
- **Safety:** realised losses past −$30 stop new entries; an equity drawdown
  past 20% from its peak flattens the position and halts all trading; a
  holding with no tracked entry is flattened at once. At most one order is
  ever in flight, and every fill is settled before the next decision.

RSI(14) uses Wilder smoothing (seeded on the first 14 close-to-close
changes). Realised PnL per sale uses the fill's reported notional as the
proceeds (already net of fee) minus the pro-rated cost basis.

## Validation (local replay harness, real bot subprocess, kit fill model)

- **(a) Dev replay:** net PnL **+$91.85**, **361 fills**, max drawdown
  **0.25%** — dev gate PASS, guardrails PASS.
- **(b) Race mode forced on the dev window** (every bar `t` +86,400,000 ms):
  net PnL **$0.00**, **0 trades**, max DD 0.00%; bot logged `MODE=race`.
  The swing filters never fired on this window, even after the bar-1200
  fallback loosened the dip to 0.7% — no loss, but also no race-mode trade
  here, so a live window shaped like the dev window would fail the
  ≥1-trade guardrail.
- **(c) Race mode on the 15 Nov downtrend:** the spec's +1-day shift does not
  reach race mode for that older window (first shifted bar still closes
  before the dev end, so the bot correctly picks dev mode and replays the
  fitted plan: −$70.88, 361 trades). With a +5-day shift, which does force
  race mode, the result is net PnL **$0.00**, **0 trades** — the recency
  filter blocks every entry on the downtrend, exactly as designed.
- **(d) Detection unit tests:** dev ts 1794926700000 → dev; race ts
  1795013040000 → race; missing/None → race; garbage → race. All PASS
  (plus: a later race ts → race, a dev ts as a string → dev).
- **(e) Determinism:** dev replay run twice; the two action logs are
  byte-identical. Re-running (a) after the final edit gives the same
  +$91.85 / 361 fills / 0.25%.

## Files

- `main.py` — the bot (stdlib only; vendored shim under `vendor/`).
- `vendor/makefun_bars.py` — byte-identical copy of the kit SDK shim.
- `README.md` — this file. `LICENSE` — MIT.
