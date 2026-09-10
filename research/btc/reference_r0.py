"""Synthetic spot accounting reference; not an execution or strategy interface."""
import re
from datetime import datetime, timedelta
from decimal import Decimal, Context, localcontext, ROUND_HALF_EVEN


class InputError(ValueError):
    pass


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value):
        raise InputError('decimal_string_required')
    return Decimal(value)


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value):
        raise InputError('UTC_required')
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError as exc:
        raise InputError('invalid_date') from exc


def run(opens, orders, step='0.001', fee_bps='0', slippage_bps='0'):
    """Return event rows. All input validation completes before any accounting."""
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        step, fee, slip = map(amount, (step, fee_bps, slippage_bps))
        if step <= 0 or not 0 <= fee <= 100 or not 0 <= slip <= 100:
            raise InputError('invalid_rules')
        if not opens:
            raise InputError('empty_opens')
        bars = [(timestamp(t), amount(p)) for t, p in opens]
        if any(p <= 0 for _, p in bars):
            raise InputError('invalid_price')
        if any(b[0]-a[0] != timedelta(hours=1) for a, b in zip(bars, bars[1:])):
            raise InputError('noncontinuous_opens')
        scheduled, expired = {}, []
        previous = None
        for order in orders:
            if set(order) != {'decision', 'available', 'side', 'quantity'}:
                raise InputError('order_schema')
            decision, available = timestamp(order['decision']), timestamp(order['available'])
            quantity = amount(order['quantity'])
            if quantity < 0 or order['side'] not in ('buy', 'sell'):
                raise InputError('invalid_order')
            if not bars[0][0] <= decision <= available <= bars[-1][0]:
                raise InputError('unavailable_input')
            if previous is not None and decision <= previous:
                raise InputError('decision_order')
            previous = decision
            slot = int((available-bars[0][0]).total_seconds() // 3600) + 1
            if slot in scheduled:
                raise InputError('colliding_orders')
            scheduled[slot] = (order['side'], quantity)
            if slot >= len(bars):
                expired.append(order.copy())
        cash, inventory, fees, implicit, gross = map(Decimal, ('1000','0','0','0','0'))
        rows = []
        for index, (time, price) in enumerate(bars):
            disposition, reason = 'hold', None
            filled, fill_price, fill_fee, signed = Decimal(0), None, Decimal(0), Decimal(0)
            unused = Decimal(0)
            if index in scheduled:
                side, requested = scheduled[index]
                # Integer ratios avoid rounding a near-integer quotient upward before flooring.
                rn, rd = requested.as_integer_ratio()
                sn, sd = step.as_integer_ratio()
                units = (rn*sd)//(rd*sn)
                parts = step.as_tuple()
                coefficient = int(''.join(map(str, parts.digits)))*units
                q = Decimal((0, tuple(map(int, str(coefficient))), parts.exponent))
                unused = requested-q
                sign = Decimal(1 if side == 'buy' else -1)
                candidate = price*(1+sign*slip/10000)
                commission = q*candidate*fee/10000
                if q == 0:
                    reason = 'zero_quantity'
                elif side == 'buy' and inventory:
                    reason = 'existing_position'
                elif side == 'buy' and q*candidate+commission > cash:
                    reason = 'insufficient_cash'
                elif side == 'buy' and q*candidate > (cash+inventory*price)*Decimal('0.25'):
                    reason = 'allocation'
                elif side == 'sell' and q > inventory:
                    reason = 'inventory'
                if reason:
                    disposition = 'rejected'
                else:
                    disposition = 'filled'
                    filled, fill_price, fill_fee, signed = q, candidate, commission, sign*q
                    cash -= signed*candidate+commission
                    inventory += signed
                    fees += commission
                    implicit += q*abs(candidate-price)
                    gross -= signed*price
            expiries = expired if index == len(bars)-1 else []
            if expiries and disposition == 'hold':
                disposition = 'expired'
            rows.append(dict(timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                             cash=cash, inventory=inventory, equity=cash+inventory*price,
                             diagnostic_return=(cash+inventory*price)/Decimal('1000')-1,
                             fees=fees, implicit=implicit, gross_cashflow=gross,
                             disposition=disposition, reason=reason, quantity=filled,
                             signed_quantity=signed, fill_price=fill_price, fill_fee=fill_fee,
                             unused_quantity=unused, expiries=expiries))
        return rows
