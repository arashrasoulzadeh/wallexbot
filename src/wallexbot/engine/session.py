"""TradingSession: the loop body shared by the backtester and the live paper engine.

It owns everything that happens when the grid meets the simulated exchange, so that a backtest and
a live paper run behave identically:

- start: place the initial grid, buying the starting coins as a simulated taker (decision D2);
- every price: offer it to the exchange as a trade, report fills to the strategy, place the
  counter-orders the strategy asks for;
- orders the exchange refuses because of its request-rate limit are *deferred* and retried on
  later ticks (a delay, not a failure); other refusals are counted and the strategy is told to
  forget the order;
- placing is idempotent: an order whose client id already exists on the exchange is adopted.
"""

from collections import deque
from decimal import ROUND_UP, Decimal
from typing import Any

from wallexbot.domain.market import OrderType, Side, Symbol
from wallexbot.domain.order import Fill, OrderRequest
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.sim.rate_limiter import RateLimitExceeded
from wallexbot.strategy.grid.interface import (
    Action,
    AlertAction,
    CancelAction,
    GridStrategy,
    PauseAction,
    PlaceAction,
)

# Each price point offers this much volume, i.e. effectively unlimited liquidity.
UNLIMITED_VOLUME = Decimal("1000000000000")


class TradingSession:
    """Drives one `GridStrategy` against one `SimulatedExchange`."""

    STATE_VERSION = 1
    RECENT_FILLS = 50  # newest fills kept in a saved state, for display

    def __init__(
        self,
        strategy: GridStrategy,
        exchange: SimulatedExchange,
        keep_fills: int | None = None,
        keep_events: int | None = None,
    ) -> None:
        """`keep_fills` / `keep_events` cap the in-memory history for runs that never end
        (a backtest keeps everything: None)."""
        self.strategy = strategy
        self.exchange = exchange
        self.keep_fills = keep_fills
        self.keep_events = keep_events
        self.fills: list[Fill] = []
        self.fill_count = 0  # every fill ever, even when old ones are dropped from `fills`
        self.fill_rows: deque[dict[str, Any]] = deque(maxlen=self.RECENT_FILLS)
        self.events: list[str] = []
        self.event_count = 0
        self.rejected = 0
        self.fees_quote = Decimal(0)  # all fees paid, valued in quote asset
        self._order_ids: dict[str, str] = {}  # strategy client_id -> exchange order id
        self._deferred: deque[PlaceAction] = deque()
        self._out_of_range = False

    @property
    def deferred_count(self) -> int:
        """Orders waiting for the exchange's request-rate window to open."""
        return len(self._deferred)

    def _event(self, message: str) -> None:
        self.events.append(message)
        self.event_count += 1
        if self.keep_events is not None and len(self.events) > self.keep_events:
            del self.events[: len(self.events) - self.keep_events]

    # --- lifecycle ------------------------------------------------------------------

    def start(self, price: Decimal, timestamp: int) -> None:
        """Place the initial grid around `price`."""
        actions = self.strategy.on_start(price, timestamp)
        self._seed_inventory(actions, price)
        self.execute(actions)
        self._out_of_range = not self._in_range(price)

    def on_tick(self, price: Decimal, timestamp: int) -> list[Fill]:
        """Process one price point; returns the fills it caused."""
        self._flush_deferred()

        inside = self._in_range(price)
        already_out = self._out_of_range
        if not inside and not already_out:
            params = self.strategy.params
            self._event(
                f"price {price} left the grid range [{params.lower_price}, {params.upper_price}]"
            )
        self._out_of_range = not inside

        actions = self.strategy.on_price(price, timestamp)
        if already_out:
            # the strategy repeats its pause/warning on every price while out of range; it was
            # announced when the price left, so do not flood the event log with copies
            actions = [a for a in actions if not isinstance(a, (PauseAction, AlertAction))]
        self.execute(actions)
        fills = self.exchange.process_trade(price, UNLIMITED_VOLUME, timestamp)
        self._on_fills(fills)
        return fills

    def stop(self, timestamp: int = 0) -> int:
        """Cancel every resting and deferred order; returns how many exchange orders were open."""
        open_before = len(self.exchange.open_orders())
        self.execute(self.strategy.on_stop(timestamp))
        self._deferred.clear()
        for order in self.exchange.open_orders():  # anything the strategy did not know about
            self.exchange.cancel_order(order.id)
        return open_before

    def equity(self, price: Decimal) -> Decimal:
        """Quote + base valued at `price` (locked funds count: they are still ours)."""
        balances = self.exchange.balances()
        market = self.exchange.market_info()
        quote = balances.get(market.quote)
        base = balances.get(market.base)
        return (quote.total if quote else Decimal(0)) + (base.total * price if base else Decimal(0))

    # --- saving and restoring (crash recovery) ---------------------------------------

    def export_state(self) -> dict[str, Any]:
        """Exchange, strategy and session bookkeeping as plain JSON types."""
        return {
            "version": self.STATE_VERSION,
            "exchange": self.exchange.export_state(),
            "strategy": self.strategy.export_state(),
            "fees_quote": str(self.fees_quote),
            "rejected": self.rejected,
            "fill_count": self.fill_count,
            "fill_rows": list(self.fill_rows),
            "event_count": self.event_count,
            "events": self.events[-200:],
            "out_of_range": self._out_of_range,
            "order_ids": dict(self._order_ids),
            "deferred": [
                {
                    "client_id": a.client_id,
                    "symbol": str(a.symbol),
                    "side": a.side.value,
                    "price": str(a.price),
                    "quantity": str(a.quantity),
                    "level_index": a.level_index,
                }
                for a in self._deferred
            ],
        }

    def import_state(self, saved: dict[str, Any]) -> None:
        """Restore a saved state into this (fresh) session."""
        if saved.get("version") != self.STATE_VERSION:
            raise ValueError(f"unsupported session state version {saved.get('version')!r}")
        self.strategy.import_state(saved["strategy"])  # checks the grid matches first
        self.exchange.import_state(saved["exchange"])
        self.fees_quote = Decimal(saved["fees_quote"])
        self.rejected = saved["rejected"]
        self.fill_count = saved["fill_count"]
        self.fill_rows = deque(saved["fill_rows"], maxlen=self.RECENT_FILLS)
        self.event_count = saved["event_count"]
        self.events = list(saved["events"])
        self._out_of_range = saved["out_of_range"]
        self._order_ids = dict(saved["order_ids"])
        self.fills = []
        self._deferred = deque(
            PlaceAction(
                type="place",
                client_id=d["client_id"],
                symbol=Symbol(d["symbol"]),
                side=Side(d["side"]),
                order_type=OrderType.LIMIT,
                price=Decimal(d["price"]),
                quantity=Decimal(d["quantity"]),
                level_index=d["level_index"],
            )
            for d in saved["deferred"]
        )

    # --- actions --------------------------------------------------------------------

    def execute(self, actions: list[Action]) -> None:
        """Send strategy actions to the exchange; failures are counted, never fatal."""
        for action in actions:
            if isinstance(action, PlaceAction):
                self._place(action)
            elif isinstance(action, CancelAction):
                self._cancel(action)
            elif isinstance(action, PauseAction):
                self._event(f"paused: {action.reason}")
            elif isinstance(action, AlertAction):
                self._event(f"{action.severity}: {action.message}")

    def _place(self, action: PlaceAction) -> bool:
        """Place one order. Returns False only when it was deferred by the rate limit."""
        existing = self.exchange.get_order_by_client_id(action.client_id)
        if existing is not None:  # a retry of something that already went through
            self._order_ids[action.client_id] = existing.id
            return True

        request = OrderRequest(
            client_id=action.client_id,
            symbol=action.symbol,
            side=action.side,
            type=OrderType.LIMIT,
            price=action.price,
            quantity=action.quantity,
        )
        try:
            order = self.exchange.place_order(request)
        except RateLimitExceeded:
            self._deferred.append(action)
            return False
        except (ValueError, RuntimeError) as exc:
            # Not enough funds, below the minimum size...: the order never existed, so the
            # strategy must forget it, otherwise it would wait for a fill forever.
            self.rejected += 1
            self._event(f"rejected {action.side.value} level {action.level_index}: {exc}")
            self.strategy.on_cancel(action.level_index)
            return True
        self._order_ids[action.client_id] = order.id
        return True

    def _cancel(self, action: CancelAction) -> None:
        for waiting in list(self._deferred):
            if waiting.client_id == action.client_id:
                self._deferred.remove(waiting)
                return
        order_id = self._order_ids.get(action.client_id)
        if order_id is not None:
            try:
                self.exchange.cancel_order(order_id)
            except ValueError:
                pass  # already filled or cancelled

    def _flush_deferred(self) -> None:
        pending = list(self._deferred)
        self._deferred.clear()
        for index, action in enumerate(pending):
            if not self._place(action):  # rate limited again: keep it and everything behind it
                self._deferred.extend(pending[index + 1 :])
                break

    # --- fills ----------------------------------------------------------------------

    def _on_fills(self, fills: list[Fill]) -> None:
        for fill in fills:
            self.fills.append(fill)
            if self.keep_fills is not None and len(self.fills) > self.keep_fills:
                del self.fills[: len(self.fills) - self.keep_fills]
            self.fill_count += 1
            self.fees_quote += self._fee_in_quote(fill)
            order = self.exchange.get_order(fill.order_id)
            self.fill_rows.append(
                {
                    "time": fill.timestamp,
                    "side": order.side.value,
                    "price": str(fill.price),
                    "quantity": str(fill.quantity),
                    "fee": str(fill.fee),
                    "fee_asset": fill.fee_asset,
                }
            )
            state = self.strategy.state
            level = state.get_level_for_order(order.client_id) if state else None
            if level is None:
                continue
            self.execute(
                self.strategy.on_fill(
                    level, fill.quantity, fill.fee, fill.fee_asset, fill.timestamp
                )
            )

    def _fee_in_quote(self, fill: Fill) -> Decimal:
        if fill.fee_asset == self.exchange.market_info().base:
            return fill.fee * fill.price
        return fill.fee

    # --- helpers --------------------------------------------------------------------

    def _in_range(self, price: Decimal) -> bool:
        params = self.strategy.params
        return params.lower_price <= price <= params.upper_price

    def _seed_inventory(self, actions: list[Action], price: Decimal) -> None:
        """Decision D2: buy the coins the initial sell levels need, as a simulated taker."""
        needed = sum(
            (a.quantity for a in actions if isinstance(a, PlaceAction) and a.side == Side.SELL),
            Decimal(0),
        )
        if needed <= 0:
            return
        market = self.exchange.market_info()
        taker = self.exchange.fee_schedule().taker_rate
        step = market.amount_step
        # Buy a little extra so that what is left after the base-asset fee still covers the sells.
        gross = (needed / (1 - taker) / step).to_integral_value(rounding=ROUND_UP) * step
        try:
            fill = self.exchange.instant_buy(price, gross)
        except ValueError as exc:
            self._event(f"could not buy starting inventory: {exc}")
            return
        self.fees_quote += fill.fee * price
