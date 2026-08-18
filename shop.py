from decimal import Decimal
from sqlalchemy import select
from app.models import Variant, CustomPrice, Coupon

async def effective_price(db, telegram_id: int, variant: Variant) -> Decimal:
    result = await db.execute(
        select(CustomPrice).where(
            CustomPrice.telegram_id == telegram_id,
            CustomPrice.variant_id == variant.id
        )
    )
    custom = result.scalar_one_or_none()
    return Decimal(custom.price) if custom else Decimal(variant.price)

async def apply_coupon(db, code: str, amount: Decimal) -> Decimal:
    result = await db.execute(
        select(Coupon).where(Coupon.code == code.upper(), Coupon.active.is_(True))
    )
    coupon = result.scalar_one_or_none()
    if not coupon:
        return amount
    discount = amount * Decimal(coupon.discount_percent) / Decimal(100)
    return max(Decimal("0"), amount - discount)
