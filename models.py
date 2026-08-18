from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, BigInteger, Boolean, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18,2), default=0)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category = relationship("Category", back_populates="products")
    variants = relationship("Variant", back_populates="product", cascade="all, delete-orphan")

class Variant(Base):
    __tablename__ = "variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[Decimal] = mapped_column(Numeric(18,2))
    stock: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    product = relationship("Product", back_populates="variants")
    custom_prices = relationship("CustomPrice", back_populates="variant", cascade="all, delete-orphan")

class CustomPrice(Base):
    __tablename__ = "custom_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(18,2))
    variant = relationship("Variant", back_populates="custom_prices")

class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5,2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18,2))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    payment_method: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
