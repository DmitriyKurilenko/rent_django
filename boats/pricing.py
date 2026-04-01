"""Unified pricing logic for search, boat detail, offers and booking."""
from typing import Any, Dict, Optional, Tuple

from boats.helpers import calculate_final_price_with_discounts
from boats.models import BoatPrice


def _to_float(value: Any) -> float:
    """Best-effort float conversion with safe fallback."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_price_components(payload: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Extract base price and discounts from Boataround payload.

    Supports both search payload and /price/<slug> payload.
    Returns: (base_price, discount_without_extra, additional_discount)
    """
    def _extract_with_presence(container: Dict[str, Any], *keys: str) -> Tuple[float, bool]:
        if not isinstance(container, dict):
            return 0.0, False
        for key in keys:
            if key not in container:
                continue
            raw = container.get(key)
            if raw is None or raw == "":
                continue
            return _to_float(raw), True
        return 0.0, False

    # Canonical values: policies[0].prices. Верхний уровень search API нестабилен
    # (totalPrice/discount могут колебаться между одинаковыми запросами).
    policy_prices: Dict[str, Any] = {}
    policies = payload.get("policies") or []
    if isinstance(policies, list) and policies:
        first_policy = policies[0] or {}
        maybe_prices = first_policy.get("prices") or {}
        if isinstance(maybe_prices, dict):
            policy_prices = maybe_prices

    policy_base_price, has_policy_base = _extract_with_presence(policy_prices, "price")
    policy_discount_wo_extra, has_policy_discount_wo_extra = _extract_with_presence(
        policy_prices, "discount_without_additionalExtra"
    )
    policy_additional_discount, has_policy_additional_discount = _extract_with_presence(
        policy_prices, "additional_discount"
    )

    top_base_price, has_top_base = _extract_with_presence(payload, "price", "totalPrice")
    top_total_price, has_top_total = _extract_with_presence(payload, "totalPrice")
    top_additional_discount, has_top_additional_discount = _extract_with_presence(
        payload, "additional_discount", "additionalDiscount"
    )
    top_explicit_discount_wo_extra, has_top_explicit_discount_wo_extra = _extract_with_presence(
        payload, "discount_without_additionalExtra", "discountWithoutAdditional"
    )
    total_discount, has_total_discount = _extract_with_presence(payload, "discount")

    base_price = policy_base_price if has_policy_base else top_base_price
    additional_discount = (
        policy_additional_discount
        if has_policy_additional_discount
        else top_additional_discount
    )

    if has_policy_discount_wo_extra:
        discount_without_extra = policy_discount_wo_extra
    elif has_top_explicit_discount_wo_extra:
        discount_without_extra = top_explicit_discount_wo_extra
    elif has_total_discount and (has_policy_additional_discount or has_top_additional_discount):
        discount_without_extra = max(total_discount - additional_discount, 0)
    elif has_total_discount:
        discount_without_extra = total_discount
    else:
        discount_without_extra = 0.0

    # Fallback для search payload без policies.prices:
    # иногда top-level discount поля противоречат totalPrice.
    # В этом случае приводим discount_without_extra к значению,
    # которое воспроизводит totalPrice (аддитивная модель скидок).
    if (not has_policy_discount_wo_extra) and has_top_total and base_price > 0:
        total_discount_pct = discount_without_extra + additional_discount
        calc_final = base_price * (1 - total_discount_pct / 100)

        if abs(calc_final - top_total_price) > 1:
            # Обратная задача: найти discount_without_extra при аддитивной модели
            # top_total_price = base_price * (1 - (discount_without_extra + additional_discount) / 100)
            # => discount_without_extra = (1 - top_total_price / base_price) * 100 - additional_discount
            if base_price > 0:
                discount_without_extra = max(
                    (1 - (top_total_price / base_price)) * 100 - additional_discount,
                    0,
                )

    return base_price, discount_without_extra, additional_discount


def build_price_breakdown(
    base_price: float,
    discount_without_extra: float,
    additional_discount: float,
    charter: Optional[Any] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """Calculate final/old/discount prices with a single formula."""
    base_price = _to_float(base_price)
    discount_without_extra = _to_float(discount_without_extra)
    additional_discount = _to_float(additional_discount)

    # Определяем доп. скидку от чартера для расшифровки
    charter_commission = float(charter.commission) if charter and getattr(charter, 'commission', None) else 0.0
    try:
        from boats.models import PriceSettings
        ps = PriceSettings.get_settings()
        extra_discount_max = float(ps.extra_discount_max)
        agent_pct = float(ps.agent_commission_pct) / 100.0
    except Exception:
        extra_discount_max = 5.0
        agent_pct = 0.5
    agent_commission_pct = charter_commission * agent_pct
    extra_discount_applied = 0.0
    additional_discount_val = additional_discount
    if additional_discount_val < charter_commission:
        extra_discount_applied = min(extra_discount_max, charter_commission)

    final_price = _to_float(
        calculate_final_price_with_discounts(
            base_price,
            discount_without_extra,
            additional_discount,
            charter=charter,
        )
    )

    # Агентская комиссия = 50% от комиссии чартера, в деньгах
    agent_commission = round(final_price * agent_commission_pct / 100, 2) if agent_commission_pct else 0.0
    # Комиссия чартера в деньгах
    charter_commission_amount = round(final_price * charter_commission / 100, 2) if charter_commission else 0.0

    old_price = 0.0
    discount_percent = 0
    if base_price > 0 and final_price > 0 and base_price > final_price:
        old_price = base_price
        try:
            discount_percent = round((base_price - final_price) / base_price * 100)
        except ZeroDivisionError:
            discount_percent = 0

    return {
        "base_price": round(base_price, 2),
        "final_price": round(final_price, 2),
        "discount_without_extra": round(discount_without_extra, 2),
        "additional_discount": round(additional_discount, 2),
        "old_price": round(old_price, 2),
        "discount_percent": int(discount_percent),
        "currency": currency or "EUR",
        "charter_commission": round(charter_commission, 2),
        "charter_commission_amount": round(charter_commission_amount, 2),
        "agent_commission": round(agent_commission, 2),
        "extra_discount_applied": round(extra_discount_applied, 2),
    }


def get_db_fallback_price(
    slug: str,
    rental_days: Optional[int] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """Fallback to stored boat prices in DB when live API price is unavailable."""
    days = rental_days if rental_days and rental_days > 0 else 7
    db_price = (
        BoatPrice.objects.filter(boat__slug=slug, currency=currency).first()
        or BoatPrice.objects.filter(boat__slug=slug).first()
    )
    if not db_price:
        return {
            "base_price": 0.0,
            "final_price": 0.0,
            "discount_without_extra": 0.0,
            "additional_discount": 0.0,
            "old_price": 0.0,
            "discount_percent": 0,
            "currency": currency,
            "source": "none",
        }

    per_day = _to_float(db_price.price_per_day)
    per_week = _to_float(db_price.price_per_week)
    total = 0.0
    if per_day > 0:
        total = round(per_day * days, 2)
    elif per_week > 0:
        total = round((per_week / 7) * days, 2)

    return {
        "base_price": total,
        "final_price": total,
        "discount_without_extra": 0.0,
        "additional_discount": 0.0,
        "old_price": 0.0,
        "discount_percent": 0,
        "currency": db_price.currency or currency,
        "source": "db",
    }


def resolve_live_or_fallback_price(
    slug: str,
    check_in: str,
    check_out: str,
    lang: str,
    charter: Optional[Any] = None,
    rental_days: Optional[int] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """
    Unified resolver:
    1) Try Boataround live price API
    2) Fallback to DB stored BoatPrice
    """
    from boats.boataround_api import BoataroundAPI

    price_data = BoataroundAPI.get_price(
        slug=slug,
        check_in=check_in,
        check_out=check_out,
        currency=currency,
        lang=lang,
    )
    if price_data:
        base_price, discount_wo_extra, additional_discount = extract_price_components(price_data)
        breakdown = build_price_breakdown(
            base_price=base_price,
            discount_without_extra=discount_wo_extra,
            additional_discount=additional_discount,
            charter=charter,
            currency=currency,
        )
        breakdown["source"] = "api"
        return breakdown

    return get_db_fallback_price(slug=slug, rental_days=rental_days, currency=currency)
