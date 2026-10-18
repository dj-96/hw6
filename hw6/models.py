"""Structured types for the vendor desk agent."""
from typing import Literal

from pydantic import BaseModel, Field


class VendorDecision(BaseModel):
    """What the agent reports for one vendor document (handbook section 13)."""

    vendor: str = Field(description="Vendor company name exactly as the document gives it.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. CC-HD-006. None if the document does not say.")
    item: str | None = Field(description="Item name from the document. None if not stated.")
    unit_price: float | None = Field(description="Quoted price per unit in USD. None if not stated.")
    lead_time_days: int | None = Field(description="Lead time in days, as the number the document states. None if not stated.")
    min_order: int | None = Field(description="Minimum order in units. None if not stated.")
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="'recommend' only if all four handbook purchasing checks pass."
    )
    reason: str = Field(description="One sentence naming the purchasing check that decided it.")
