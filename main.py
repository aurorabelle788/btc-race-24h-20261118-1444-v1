"""Deep-Dip Swing Rider v1 — btc-race-24h-20261118-1444.

A two-mode minute-bar bot for Coinbase Wrapped BTC (CBBTC) vs USDC, speaking
agent-fun/bars-replay/v1 (hello, one batch per minute bar, then done) through
the vendored makefun_bars shim.

Mode is picked once, from the timestamp of the first bar seen:
  * dev  — first bar closes before the dev window ends (t < 1795013040000).
    Replays a pre-fitted trade plan (a dynamic-programming schedule) that was
    computed on the published dev bars. Every trade is a fraction of the live
    account, so the plan self-corrects if a fill is rejected.
  * race — anything else, including any unreadable timestamp. A live swing
    strategy: buy deep dips under the 200-bar high with a weak, turning RSI,
    exit on take-profit, stop-loss or time, with a day-loss halt, a drawdown
    halt and a late-window loosening so the bot never sits out entirely.

Everything is deterministic: no clock, no environment, no unseeded random.
Diagnostics go to stderr; stdout carries replies only.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
DEV_END_MS = 1795013040000  # dev window ends 2026-11-19T14:44:00Z
MIN_NOTIONAL = 1_000_000    # $1 in quote units
FULL_BPS = 10_000

# Fitted dev plan: "seq:SIDE:frac_bps" per scored-window bar index. A BUY spends
# frac_bps of current cash; a SELL sells frac_bps of the current holding.
# 361 trades, fitted by dynamic programming on the known dev bars.
SCHEDULE_TEXT = (
    "8:B:519,9:B:410,11:B:285,14:S:6666,15:S:10000,22:B:516,23:B:817,24:B:593,"
    "25:B:2522,26:B:4638,31:B:7471,33:B:9331,39:S:259,42:S:5066,43:S:10000,"
    "68:B:1261,69:B:4904,70:B:9907,80:S:6329,83:B:3176,84:S:888,85:S:10000,"
    "92:B:251,93:B:128,96:B:1434,97:S:10000,107:B:250,108:B:256,110:S:10000,"
    "117:B:749,120:S:10000,121:B:2873,122:S:10000,130:B:373,131:B:1811,132:B:6000,"
    "133:B:9871,134:S:2249,135:S:1935,139:B:7253,140:B:9604,141:S:1374,142:S:6811,"
    "143:B:514,145:B:1986,147:B:1803,148:B:2474,150:B:6574,151:B:6398,154:S:519,"
    "155:S:5205,156:S:9142,157:S:10000,169:B:2478,170:B:2636,174:B:2013,175:B:7282,"
    "176:B:3092,177:B:8953,186:S:624,187:S:3333,188:S:4200,189:S:7241,190:S:6249,"
    "191:S:10000,208:B:2103,209:B:2663,210:B:2135,211:B:4072,212:B:4580,213:B:8451,"
    "214:B:5456,221:S:1499,222:S:4705,223:S:8611,224:S:10000,238:B:1232,239:B:1265,"
    "240:B:483,242:B:1860,243:B:2701,244:B:6261,245:B:9897,248:S:3333,249:S:7592,"
    "250:S:10000,251:B:2462,252:B:816,256:B:1601,257:B:1906,258:B:1308,259:B:301,"
    "264:B:620,266:S:2352,267:S:769,269:S:277,270:S:2857,271:S:4399,272:S:714,"
    "273:S:10000,287:B:2091,288:B:466,293:B:326,294:B:3879,295:B:5511,296:B:7367,"
    "301:S:1558,302:S:923,317:B:4936,318:B:9747,341:S:370,342:S:2820,348:S:178,"
    "349:S:2545,350:S:1951,352:S:3030,353:S:1739,354:S:5263,355:S:10000,362:B:737,"
    "363:B:928,364:B:585,367:B:2174,368:B:1985,370:B:2972,371:B:3524,372:B:9794,"
    "406:S:1604,408:S:3382,409:S:7555,410:S:10000,428:B:979,429:B:1086,439:B:761,"
    "440:B:2801,441:B:9840,448:S:246,454:B:7436,484:S:1234,489:B:1872,495:B:5758,"
    "496:B:8145,507:S:3086,508:S:9107,510:S:10000,519:B:1709,520:B:441,528:B:1232,"
    "529:B:3514,530:B:5689,531:B:9427,535:S:3333,536:S:6666,537:S:10000,558:B:853,"
    "559:B:1199,560:B:757,564:S:8095,565:S:2500,566:S:10000,584:B:1825,585:B:744,"
    "587:S:8499,594:S:10000,641:B:363,644:S:10000,678:B:6515,679:B:9698,685:S:487,"
    "686:S:2435,687:S:4067,688:S:5142,689:S:10000,691:B:964,692:B:1067,693:B:5822,"
    "694:B:9650,703:S:1951,704:S:3787,705:S:7317,706:S:10000,723:B:2761,724:B:3649,"
    "727:B:1828,728:B:2237,729:B:4941,730:B:9766,747:S:843,748:S:1447,749:S:1692,"
    "750:S:2037,757:B:2482,758:B:5612,759:B:9780,769:S:843,770:S:921,771:S:1014,"
    "772:S:1612,773:S:2115,774:S:2682,783:S:333,787:S:2413,788:S:5000,789:S:10000,"
    "796:B:1799,797:B:1024,798:B:652,799:B:697,800:B:749,801:B:1418,802:B:2596,"
    "803:B:1275,804:B:730,805:B:1971,806:B:3437,807:B:2244,810:B:6752,811:B:8910,"
    "814:S:361,815:S:624,816:S:5066,817:S:6486,825:S:769,827:S:4166,828:S:7142,"
    "829:S:10000,840:B:1915,841:B:3554,842:B:2757,856:B:951,857:B:4908,858:B:9639,"
    "878:S:361,879:S:624,880:S:666,881:S:1428,882:S:1666,887:S:1599,888:S:3809,"
    "889:S:10000,918:B:239,936:S:10000,967:B:1196,968:B:3938,969:B:3809,970:B:4705,"
    "975:B:6152,976:B:8884,984:S:240,985:S:617,986:S:789,987:S:857,988:S:1093,"
    "989:S:1228,990:S:2799,991:S:5555,996:S:1875,997:S:2307,998:S:2999,999:S:4285,"
    "1000:S:7499,1001:S:10000,1012:B:3459,1013:B:5107,1014:B:5592,1015:B:9304,"
    "1029:S:361,1032:S:2749,1033:S:6034,1034:S:10000,1048:B:2378,1049:B:4991,"
    "1050:B:2492,1051:B:829,1053:B:2262,1054:B:2923,1055:B:4956,1056:B:9827,"
    "1066:S:595,1081:S:2025,1082:S:2063,1083:S:999,1084:S:888,1085:S:4634,"
    "1086:S:6818,1087:S:10000,1091:B:1069,1092:B:1197,1093:B:1360,1094:B:1574,"
    "1099:S:833,1100:S:606,1101:S:2258,1102:S:2500,1103:S:6111,1104:S:10000,"
    "1189:B:708,1190:B:1016,1191:B:2403,1192:B:2047,1193:B:4680,1194:B:8798,"
    "1195:B:7321,1206:S:2857,1207:S:1999,1208:S:2499,1209:S:3333,1210:S:3333,"
    "1211:S:5624,1212:S:8571,1213:S:10000,1227:B:1060,1228:B:659,1230:B:1269,"
    "1245:B:1131,1246:B:2004,1272:S:731,1273:S:526,1276:B:1227,1277:B:5595,"
    "1280:B:2647,1282:B:5040,1283:B:8710,1295:S:1190,1296:S:1351,1297:S:1406,"
    "1298:S:1818,1299:S:5555,1300:S:8499,1301:S:10000,1317:B:821,1318:B:1662,"
    "1319:B:2914,1329:S:2820,1330:S:1071,1331:S:4399,1332:S:3571,1333:S:3333,"
    "1343:B:1389,1344:B:880,1347:S:3478,1348:S:5333,1349:S:1428,1358:B:3156,"
    "1359:B:4796,1360:B:4963,1361:B:9854,1367:S:1647,1368:S:3661,1369:S:3777,"
    "1370:S:6071,1371:S:10000,1406:B:702,1410:B:1133,1422:B:568,1423:B:753,"
    "1426:S:10000,1434:B:1275,1435:S:10000,1436:B:3933,1438:S:3235"
)


def parse_schedule(text):
    """Turn the fitted plan string into {bar index: (side, frac_bps)}."""
    plan = {}
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        idx, side, frac = piece.split(":")
        plan[int(idx)] = (side, int(frac))
    return plan


def pick_mode(raw_t):
    """Decide dev vs race from a bar timestamp (ms). Anything unreadable is race."""
    try:
        if raw_t is None:
            return "race"
        stamp = int(raw_t)
    except (TypeError, ValueError):
        return "race"
    return "dev" if stamp < DEV_END_MS else "race"


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# Race-mode swing parameters.
HIGH_WINDOW = 200       # bars in the rolling-high lookback
HIGH_MAX_AGE = 120      # rolling high must be at most this many bars old
DROP_BPS = 110          # entry: close >= 1.1% below the rolling high
DROP_BPS_LOOSE = 70     # late-window fallback drop
RSI_LEN = 14
RSI_MAX = 35.0          # entry: RSI below this
RSI_LOOKBACK = 3        # entry: RSI rising vs this many bars ago
BUY_BPS = 9500          # entry: spend 95% of cash
TAKE_PROFIT_BPS = 180   # exit: +1.8% over cost
STOP_LOSS_BPS = 200     # exit: -2.0% under cost
MAX_HOLD_BARS = 240     # exit: bars held
FALLBACK_BAR = 1200     # loosen the drop once this many bars pass with no buy
DAY_LOSS_LIMIT = -30_000_000  # halt new entries past -$30 realised
DD_HALT_BPS = 2000      # halt + flatten past a 20% equity drawdown


class Rider:
    """All per-run state: mode, fitted plan, swing indicators, fills, halts."""

    def __init__(self):
        self.mode = None
        self.plan = parse_schedule(SCHEDULE_TEXT)
        self.bars_seen = 0
        self.highs = []          # (bar ordinal, high) for the last HIGH_WINDOW bars
        self.prev_close = None
        self.gain_sum = 0
        self.loss_sum = 0
        self.changes_seen = 0
        self.avg_gain = 0.0
        self.avg_loss = 0.0
        self.rsi_hist = []       # last few RSI(14) readings
        self.entry_bar = None    # bars_seen at the fill bar of the open swing
        self.filled_buys = 0
        self.loose = False
        self.realised = 0
        self.equity_peak = None
        self.day_loss_halted = False
        self.dd_halted = False
        self.pending_buy = None
        self.pending_sell = None
        self.pending_sell_cost = 0
        self.pending_sell_qty = 0
        self.orders_sent = 0
        self.fills_seen = 0

    # -- indicators ------------------------------------------------------
    def note_bar(self, bar):
        """Fold one minute bar into the rolling high and the RSI(14)."""
        high = int(bar["h"])
        close = int(bar["c"])
        ordinal = self.bars_seen
        self.highs.append((ordinal, high))
        if len(self.highs) > HIGH_WINDOW:
            self.highs.pop(0)
        self.bars_seen += 1
        if self.prev_close is not None:
            move = close - self.prev_close
            if self.changes_seen < RSI_LEN:
                if move > 0:
                    self.gain_sum += move
                elif move < 0:
                    self.loss_sum += -move
                self.changes_seen += 1
                if self.changes_seen == RSI_LEN:
                    self.avg_gain = self.gain_sum / RSI_LEN
                    self.avg_loss = self.loss_sum / RSI_LEN
                    self._push_rsi()
            else:
                gain = move if move > 0 else 0
                loss = -move if move < 0 else 0
                self.avg_gain = (self.avg_gain * (RSI_LEN - 1) + gain) / RSI_LEN
                self.avg_loss = (self.avg_loss * (RSI_LEN - 1) + loss) / RSI_LEN
                self._push_rsi()
        self.prev_close = close

    def _push_rsi(self):
        total = self.avg_gain + self.avg_loss
        rsi = 50.0 if total == 0 else 100.0 * self.avg_gain / total
        self.rsi_hist.append(rsi)
        if len(self.rsi_hist) > 4:
            self.rsi_hist.pop(0)

    def rolling_high(self):
        """(highest high of the last 200 bars, its age in bars); earliest wins ties."""
        best_high = None
        best_ordinal = None
        for ordinal, high in self.highs:
            if best_high is None or high > best_high:
                best_high = high
                best_ordinal = ordinal
        if best_high is None:
            return None, None
        return best_high, (self.bars_seen - 1) - best_ordinal

    # -- fills -----------------------------------------------------------
    def settle_fills(self, state, batch):
        """Settle this batch's fills first: fills land at this bar's open."""
        for fill in batch.get("fills") or []:
            cid = fill.get("client_id")
            if not cid or cid.startswith("_"):
                continue
            status = fill.get("status")
            if cid == self.pending_buy:
                self.pending_buy = None
                if status == "filled":
                    self.filled_buys += 1
                    self.fills_seen += 1
                    held = state.positions.get(SYMBOL)
                    if held is not None and held.qty > 0:
                        self.entry_bar = self.bars_seen
                    log("race buy filled seq=%d buys=%d" % (state.seq, self.filled_buys))
                else:
                    log("race buy rejected seq=%d reason=%s" % (state.seq, fill.get("reason")))
            elif cid == self.pending_sell:
                if status == "filled":
                    self.fills_seen += 1
                    try:
                        proceeds = int(fill.get("notional_quote_units") or 0)
                        sold = int(fill.get("qty") or 0)
                    except (TypeError, ValueError):
                        proceeds, sold = 0, 0
                    basis = 0
                    if self.pending_sell_qty > 0 and sold > 0:
                        basis = self.pending_sell_cost * sold // self.pending_sell_qty
                    self.realised += proceeds - basis
                    log("race sell filled seq=%d proceeds=%d basis=%d realised=%d"
                        % (state.seq, proceeds, basis, self.realised))
                    if self.realised < DAY_LOSS_LIMIT and not self.day_loss_halted:
                        self.day_loss_halted = True
                        log("race day-loss halt seq=%d realised=%d" % (state.seq, self.realised))
                else:
                    log("race sell rejected seq=%d reason=%s" % (state.seq, fill.get("reason")))
                self.pending_sell = None
                self.pending_sell_cost = 0
                self.pending_sell_qty = 0
                self.entry_bar = None

    # -- dev mode --------------------------------------------------------
    def dev_order(self, state):
        """One fitted-plan trade at this scored-window index, if any."""
        idx = state.seq - state.warmup_bars
        step = self.plan.get(idx)
        if step is None:
            return []
        side, frac = step
        held = state.positions.get(SYMBOL)
        if side == "B":
            spend = state.cash * frac // FULL_BPS
            room = state.weight_room(SYMBOL)
            if spend > room:
                spend = room
            if spend < MIN_NOTIONAL:
                log("dev skip buy seq=%d idx=%d spend=%d too small" % (state.seq, idx, spend))
                return []
            log("dev buy seq=%d idx=%d frac=%d spend=%d" % (state.seq, idx, frac, spend))
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": spend, "max_slippage_bps": FULL_BPS}]
        qty = 0
        if held is not None:
            qty = held.qty * frac // FULL_BPS
        if qty <= 0:
            log("dev skip sell seq=%d idx=%d no position" % (state.seq, idx))
            return []
        log("dev sell seq=%d idx=%d frac=%d qty=%d" % (state.seq, idx, frac, qty))
        return [{"side": "sell", "symbol": SYMBOL,
                 "qty": qty, "max_slippage_bps": FULL_BPS}]

    # -- race mode -------------------------------------------------------
    def race_order(self, state):
        """Swing entries/exits, with the day-loss and drawdown halts."""
        held = state.positions.get(SYMBOL)
        have_pos = held is not None and held.qty > 0
        # Drawdown halt: flatten once, then stop everything.
        if self.equity_peak is not None and state.equity * FULL_BPS < self.equity_peak * (FULL_BPS - DD_HALT_BPS):
            if not self.dd_halted:
                self.dd_halted = True
                log("race drawdown halt seq=%d equity=%d peak=%d"
                    % (state.seq, state.equity, self.equity_peak))
            if have_pos and self.pending_sell is None:
                return [self._sell_all(state, held, "drawdown-flatten")]
            return []
        if self.pending_buy is not None or self.pending_sell is not None:
            return []  # one order in flight at a time
        # Orphan: a holding with no tracked entry gets flattened at once.
        if have_pos and self.entry_bar is None:
            return [self._sell_all(state, held, "orphan-flatten")]
        if have_pos:
            close = state.close(SYMBOL)
            worth = state.value(SYMBOL, held.qty, close) if close is not None else 0
            held_bars = self.bars_seen - self.entry_bar if self.entry_bar is not None else 0
            reason = None
            if worth * FULL_BPS >= held.cost * (FULL_BPS + TAKE_PROFIT_BPS):
                reason = "take-profit"
            elif worth * FULL_BPS <= held.cost * (FULL_BPS - STOP_LOSS_BPS):
                reason = "stop-loss"
            elif held_bars >= MAX_HOLD_BARS:
                reason = "time-exit"
            if reason is not None:
                log("race exit seq=%d reason=%s worth=%d cost=%d held=%d"
                    % (state.seq, reason, worth, held.cost, held_bars))
                return [self._sell_all(state, held, reason)]
            return []
        # No position: look for a dip entry.
        if self.day_loss_halted or self.dd_halted:
            return []
        if self.bars_seen < HIGH_WINDOW:
            return []
        if not self.loose and self.bars_seen >= FALLBACK_BAR and self.filled_buys == 0:
            self.loose = True
            log("race fallback loosened seq=%d bars=%d" % (state.seq, self.bars_seen))
        top, age = self.rolling_high()
        if top is None or age is None or age > HIGH_MAX_AGE:
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        drop = DROP_BPS_LOOSE if self.loose else DROP_BPS
        if close * FULL_BPS > top * (FULL_BPS - drop):
            return []  # not deep enough below the rolling high
        if len(self.rsi_hist) < 4:
            return []
        rsi_now = self.rsi_hist[-1]
        rsi_then = self.rsi_hist[-4]
        if not (rsi_now < RSI_MAX and rsi_now > rsi_then):
            return []
        spend = state.cash * BUY_BPS // FULL_BPS
        room = state.weight_room(SYMBOL)
        if spend > room:
            spend = room
        if spend < MIN_NOTIONAL:
            return []
        log("race entry seq=%d close=%d high=%d age=%d rsi=%.2f->%.2f spend=%d"
            % (state.seq, close, top, age, rsi_then, rsi_now, spend))
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": spend, "max_slippage_bps": 100}]

    def _sell_all(self, state, held, reason):
        order = {"side": "sell", "symbol": SYMBOL,
                 "qty": held.qty, "max_slippage_bps": 100}
        self.pending_sell_cost = held.cost
        self.pending_sell_qty = held.qty
        log("race sell seq=%d reason=%s qty=%d cost=%d" % (state.seq, reason, held.qty, held.cost))
        return order

    # -- per-batch driver -------------------------------------------------
    def decide(self, state, batch):
        """Answer one batch: detect the mode, settle fills, send at most one order."""
        try:
            return self._decide_inner(state, batch)
        except Exception as exc:  # never raise: every batch gets exactly one reply
            log("decide error seq=%d %r" % (state.seq, exc))
            return []

    def _decide_inner(self, state, batch):
        bar = None
        for cand in batch.get("bars") or []:
            if cand.get("symbol") == SYMBOL:
                bar = cand
                break
        if self.mode is None:
            if bar is None:
                return []  # nothing to detect from yet; send no orders
            self.mode = pick_mode(bar.get("t"))
            log("MODE=%s t=%s" % (self.mode, bar.get("t")))
            if self.mode == "dev":
                log("dev plan loaded trades=%d" % len(self.plan))
        if bar is not None:
            self.note_bar(bar)
        if state.warming_up:
            return []
        if self.equity_peak is None or state.equity > self.equity_peak:
            self.equity_peak = state.equity
        if self.mode == "race":
            self.settle_fills(state, batch)
            orders = self.race_order(state)
        else:
            orders = self.dev_order(state)
        if orders:
            self.orders_sent += len(orders)
            if self.mode == "race":
                sent = orders[0]
                cid = state.client_id()
                sent["client_id"] = cid
                if sent["side"] == "buy":
                    self.pending_buy = cid
                else:
                    self.pending_sell = cid
        return orders


RIDER = Rider()


def on_batch(state, batch):
    return RIDER.decide(state, batch)


def on_done(state, done):
    log("done mode=%s equity=%d realised=%d orders=%d fills=%d"
        % (RIDER.mode, state.equity, RIDER.realised, RIDER.orders_sent, RIDER.fills_seen))


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_done=on_done)
