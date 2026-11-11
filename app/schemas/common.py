"""Shared API schemas: Problem Details, pagination envelope, money."""

import math
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

CURRENCY_CODE = "LKR"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Monetary amounts are serialised as strings to avoid float rounding in JSON clients.
MoneyAmount = Annotated[
    Decimal,
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str, when_used="json"),
    Field(
        max_digits=12,
        decimal_places=2,
        json_schema_extra={"type": "string", "format": "decimal", "example": "125000.00"},
    ),
]


class APIModel(BaseModel):
    """Base for response models: immutable and populated from ORM attributes."""

    model_config = ConfigDict(from_attributes=True, frozen=True)


class RequestModel(BaseModel):
    """Base for request bodies: unknown fields are rejected to prevent mass assignment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Money(APIModel):
    amount: MoneyAmount = Field(description="Amount with two decimal places, as a string.")
    currency: Literal["LKR"] = Field(default=CURRENCY_CODE, description="ISO 4217 code.")


def money(amount: Decimal) -> Money:
    return Money(amount=amount, currency=CURRENCY_CODE)


class ValidationErrorItem(APIModel):
    loc: list[str] = Field(description="Location of the offending field.")
    msg: str
    type: str


class ProblemDetail(APIModel):
    """RFC 9457 Problem Details with ChronoStore extensions."""

    type: str = Field(examples=["urn:chronostore:problem:not-found"])
    title: str = Field(examples=["Resource not found"])
    status: int = Field(examples=[404])
    detail: str = Field(examples=["Product not found."])
    instance: str | None = Field(default=None, examples=["/api/v1/products/…"])
    code: str = Field(description="Stable machine-readable error code.", examples=["NOT_FOUND"])
    request_id: str | None = Field(default=None, description="Correlates with server logs.")
    errors: list[ValidationErrorItem] | None = Field(
        default=None, description="Field errors (validation failures only)."
    )


class Page[T](APIModel):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total: int = Field(ge=0, description="Total matching items across all pages.")
    total_pages: int = Field(ge=0)

    @classmethod
    def build(cls, items: list[T], *, page: int, page_size: int, total: int) -> Page[T]:
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )


class PageParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
