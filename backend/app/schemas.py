"""
Phase 2: Pydantic v2 schemas for Policy, Mapping, Plan, and core domain models.
"""

import re
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator

CONVERSION_BASES = ("transaction_date", "latest")
BLANK_CURRENCY = "(BLANK)"  # key used in Policy.currency_map for rows whose currency cell is empty

class Policy(BaseModel):
    duplicate: str = "keep_first_by_key"
    conflicting_duplicate: str = "flag_exclude_and_block_if_in_scope"
    missing: str = "exclude_if_missing_date_or_amount"
    date_format: str = "DD/MM/YYYY"
    calendar: str = "calendar_quarters"
    currency: str = "convert_by_effective_date"
    unsupported_currency: str = "block_and_list"
    refunds: str = "include_as_negative"
    target_currency: str = "INR"
    # Answers to the currency confirmation questions (see /currency/check):
    #  currency_map: {code found in the data -> code it really is}, e.g. {"USD": "USD", "EUR": "EUR", "RS": "INR"}.
    #                A code mapped to itself means "yes, that currency is correct".
    #  conversion_basis: "transaction_date" (rate in force on each row's date) or "latest" (present rate on file).
    currency_map: Dict[str, str] = Field(default_factory=dict)
    conversion_basis: Optional[str] = None

    @field_validator("currency_map")
    @classmethod
    def _clean_currency_map(cls, value: Dict[str, str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for k, v in (value or {}).items():
            key = str(k).strip().upper()
            if key in ("", "(BLANK)", "BLANK"):
                key = BLANK_CURRENCY
            code = str(v).strip().upper()
            if not re.fullmatch(r"[A-Z]{3}", code):
                raise ValueError(f"'{v}' is not a 3-letter currency code (for '{k}').")
            out[key] = code
        return out

    @field_validator("conversion_basis")
    @classmethod
    def _check_basis(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in CONVERSION_BASES:
            raise ValueError(f"conversion_basis must be one of {list(CONVERSION_BASES)}.")
        return value

class Mapping(BaseModel):
    transactions_table: str = ""
    key_column: str = ""
    date_column: str = ""
    entity_column: str = ""
    amount_column: str = ""
    currency_column: str = ""
    rates_table: str = ""
    rate_currency_column: str = ""
    rate_value_column: str = ""
    rate_effective_date_column: str = ""
    summary_table: str = ""
    summary_period_column: str = ""
    summary_amount_column: str = ""
    refunds_table: str = ""
    refund_key_column: str = ""
    refund_amount_column: str = ""
    refund_date_column: str = ""
    entity_lookup_table: str = ""
    entity_lookup_key: str = ""
    entity_lookup_label: str = ""
    unit_multiplier: float = 1.0

class MetricConfig(BaseModel):
    agg: Literal["sum", "count", "mean", "min", "max"] = "sum"
    column: str = ""
    convert_currency: Optional[Dict[str, str]] = None

class DateRange(BaseModel):
    column: str = ""
    start: str = ""
    end: str = ""

class Clarification(BaseModel):
    question: str = ""
    options: List[str] = Field(default_factory=list)
    questions: List[Dict[str, Any]] = Field(default_factory=list)

class RefusalInfo(BaseModel):
    reason: str = ""
    missing: List[str] = Field(default_factory=list)

class Plan(BaseModel):
    status: Literal["ready", "needs_clarification", "refused"] = "ready"
    intent: Literal["aggregate", "rank", "compare", "investigate", "impact", "metadata"] = "aggregate"
    tables: List[str] = Field(default_factory=list)
    metric: Optional[MetricConfig] = None
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    date_range: Optional[DateRange] = None
    group_by: List[str] = Field(default_factory=list)
    order_by: Optional[str] = None
    limit: Optional[int] = None
    comparison_entities: List[str] = Field(default_factory=list)
    requested_output: Literal["value", "rows", "ranking", "explanation"] = "value"
    policy: Dict[str, Any] = Field(default_factory=dict)
    clarification: Optional[Clarification] = None
    refusal: Optional[RefusalInfo] = None

