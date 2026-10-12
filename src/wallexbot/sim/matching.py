"""Order matching engine for simulated exchange."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from wallexbot.domain.fees import FeeSchedule
from wallexbot.domain.market import Market, OrderStatus, OrderType, Side
from wallexbot.domain.order import Fill, Order


class FillModel(str, Enum):
    """Fill model for backtesting."""

    CONSERVATIVE = "conservative"  # Needs trade THROUGH the price
    TOUCH = "touch"  # Fills on price TOUCH


@dataclass
class MatchingEngine:
    """Matches orders against price/trade feed."""

    market: Market
    fee_schedule: FeeSchedule
    fill_model: FillModel = FillModel.CONSERVATIVE
    _orders: dict[str, Order] = field(default_factory=dict)
    _stop_orders: dict[str, tuple[Order, Decimal]] = field(
        default_factory=dict
    )  # order_id -> (order, stop_price)
    _order_sequence: int = 0

    def add_order(self, order: Order) -> None:
        """Add an order to the book."""
        self._orders[order.id] = order

    def add_stop_order(self, order: Order, stop_price: Decimal) -> None:
        """Add a stop order."""
        self._stop_orders[order.id] = (order, stop_price)

    def remove_order(self, order_id: str) -> Order | None:
        """Remove and return an order."""
        return self._orders.pop(order_id, None)

    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return self._orders.get(order_id)

    def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        return [o for o in self._orders.values() if o.is_active]

    def process_trade(self, price: Decimal, quantity: Decimal, timestamp: int) -> list[Fill]:
        """
        Process a trade against open orders.

        Args:
            price: Trade price
            quantity: Trade quantity
            timestamp: Trade timestamp

        Returns:
            List of fills generated
        """
        fills: list[Fill] = []
        remaining_qty = quantity

        # Get matching orders (price-time priority)
        matching_orders = self._get_matching_orders(price, Side.BUY if price > 0 else Side.SELL)
        # For simplicity, process BUY orders when price <= limit, SELL when price >= limit

        # Process BUY orders (bids)
        for order in matching_orders["buy"]:
            if remaining_qty <= 0:
                break
            order_fills = self._fill_order(order, price, remaining_qty, timestamp, is_maker=True)
            fills.extend(order_fills)
            for f in order_fills:
                remaining_qty -= f.quantity

        # Process SELL orders (asks)
        for order in matching_orders["sell"]:
            if remaining_qty <= 0:
                break
            order_fills = self._fill_order(order, price, remaining_qty, timestamp, is_maker=True)
            fills.extend(order_fills)
            for f in order_fills:
                remaining_qty -= f.quantity

        return fills

    def process_market_order(self, order: Order) -> list[Fill]:
        """
        Process a market order against the book.

        Args:
            order: Market order to fill

        Returns:
            List of fills
        """
        # This is a simplified implementation
        # In reality, would walk the order book
        fills: list[Fill] = []
        return fills

    def check_stop_triggers(self, current_price: Decimal) -> list[Order]:
        """
        Check stop orders for triggers.

        Args:
            current_price: Current market price

        Returns:
            List of triggered stop orders (converted to limit/market)
        """
        triggered = []
        to_remove = []

        for order_id, (order, stop_price) in self._stop_orders.items():
            should_trigger = False

            if order.side == Side.BUY:
                # Stop buy triggers when price >= stop_price
                if current_price >= stop_price:
                    should_trigger = True
            else:
                # Stop sell triggers when price <= stop_price
                if current_price <= stop_price:
                    should_trigger = True

            if should_trigger:
                # Convert to limit/market order
                if order.type == OrderType.STOP_LIMIT:
                    # Keep limit price, activate
                    order = Order(
                        id=order.id,
                        client_id=order.client_id,
                        symbol=order.symbol,
                        side=order.side,
                        type=OrderType.LIMIT,
                        price=order.price,
                        quantity=order.quantity,
                        status=OrderStatus.NEW,
                        filled_quantity=Decimal("0"),
                        fee=Decimal("0"),
                        fee_asset=order.fee_asset,
                        is_maker=order.is_maker,
                        created_at=order.created_at,
                        updated_at=order.updated_at,
                    )
                elif order.type == OrderType.STOP_MARKET:
                    # Convert to market order
                    order = Order(
                        id=order.id,
                        client_id=order.client_id,
                        symbol=order.symbol,
                        side=order.side,
                        type=OrderType.MARKET,
                        price=None,
                        quantity=order.quantity,
                        status=OrderStatus.NEW,
                        filled_quantity=Decimal("0"),
                        fee=Decimal("0"),
                        fee_asset=order.fee_asset,
                        is_maker=False,
                        created_at=order.created_at,
                        updated_at=order.updated_at,
                    )

                self.add_order(order)
                triggered.append(order)
                to_remove.append(order_id)

        for oid in to_remove:
            del self._stop_orders[oid]

        return triggered

    def _get_matching_orders(self, price: Decimal, side: Side) -> dict[str, list[Order]]:
        """Get orders that match at the given price."""
        buy_orders = []
        sell_orders = []

        for order in self._orders.values():
            if not order.is_active:
                continue

            if order.type == OrderType.MARKET:
                # Market orders handled separately
                continue

            if order.side == Side.BUY:
                # Buy order matches if trade price <= limit price
                if self._price_matches_buy(order.price, price):
                    buy_orders.append(order)
            elif order.side == Side.SELL:
                # Sell order matches if trade price >= limit price
                if self._price_matches_sell(order.price, price):
                    sell_orders.append(order)

        # Sort by price-time priority
        buy_orders.sort(key=lambda o: (-o.price, o.created_at))
        sell_orders.sort(key=lambda o: (o.price, o.created_at))

        return {"buy": buy_orders, "sell": sell_orders}

    def _price_matches_buy(self, limit_price: Decimal, trade_price: Decimal) -> bool:
        """Check if trade price matches buy limit."""
        if self.fill_model == FillModel.CONSERVATIVE:
            return trade_price < limit_price  # Strictly through
        else:  # TOUCH
            return trade_price <= limit_price

    def _price_matches_sell(self, limit_price: Decimal, trade_price: Decimal) -> bool:
        """Check if trade price matches sell limit."""
        if self.fill_model == FillModel.CONSERVATIVE:
            return trade_price > limit_price  # Strictly through
        else:  # TOUCH
            return trade_price >= limit_price

    def _fill_order(
        self, order: Order, price: Decimal, available_qty: Decimal, timestamp: int, is_maker: bool
    ) -> list[Fill]:
        """Fill an order up to available quantity."""
        fills: list[Fill] = []
        remaining = order.remaining_quantity
        fill_qty = min(remaining, available_qty)

        if fill_qty <= 0:
            return fills

        # Calculate fee
        if order.side == Side.BUY:
            fee_asset = order.fee_asset  # Quote asset
            fee = self.fee_schedule.calculate_fee(price, fill_qty, Side.BUY, is_maker)
        else:
            fee_asset = order.fee_asset  # Base asset
            fee = self.fee_schedule.calculate_fee(price, fill_qty, Side.SELL, is_maker)

        # Create fill
        fill = Fill(
            order_id=order.id,
            trade_id=f"trade_{self._order_sequence}",
            price=price,
            quantity=fill_qty,
            fee=fee,
            fee_asset=fee_asset,
            is_maker=is_maker,
            timestamp=timestamp,
        )
        self._order_sequence += 1
        fills.append(fill)

        # Update order (would need mutable order or return new order)
        # For now, we'll mutate - in production use immutable updates
        object.__setattr__(order, "filled_quantity", order.filled_quantity + fill_qty)
        object.__setattr__(order, "fee", order.fee + fee)
        object.__setattr__(order, "updated_at", timestamp)

        if order.filled_quantity >= order.quantity:
            object.__setattr__(order, "status", OrderStatus.FILLED)
        else:
            object.__setattr__(order, "status", OrderStatus.PARTIALLY_FILLED)

        return fills
