"""Stage 2: Structure (the smart part).

Hand the raw statement blob from stage 1 to Claude and ask it to return clean,
structured JSON matching a fixed schema. This is what lets us absorb format
variability across processors without writing a parser per processor.

We use the Anthropic structured-outputs feature (`output_config.format` via
`messages.parse`), which constrains the response to our Pydantic schema, then
validate and retry if anything comes back malformed or refused.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

DEFAULT_MODEL = os.environ.get("ARCH_MODEL", "claude-opus-4-8")
MAX_ATTEMPTS = 3


# --------------------------------------------------------------------------- #
# Schema — the fixed shape every statement gets normalized into.
# Numeric fields are Optional because not every statement reports every line;
# the model returns null when a value genuinely isn't present rather than
# guessing.
# --------------------------------------------------------------------------- #


class CurrentModel(str, Enum):
    FLAT = "flat"
    TIERED = "tiered"
    IC_PLUS = "IC+"
    UNKNOWN = "unknown"


class FixedFees(BaseModel):
    """Recurring flat fees that aren't a percentage of volume."""

    pci: Optional[float] = Field(None, description="PCI compliance / non-compliance fee")
    monthly: Optional[float] = Field(None, description="Monthly service / account fee")
    batch: Optional[float] = Field(None, description="Total batch / settlement fees")
    statement: Optional[float] = Field(None, description="Statement / paper fee")
    other: Optional[float] = Field(
        None, description="Sum of any other fixed fees not captured above"
    )


class CardMixEntry(BaseModel):
    card_type: str = Field(description="e.g. Visa, Mastercard, Amex, Discover, Debit")
    volume: Optional[float] = Field(None, description="Dollar volume for this card type")
    percentage: Optional[float] = Field(
        None, description="Share of total volume, 0-100, if reported"
    )


class Statement(BaseModel):
    """Normalized merchant statement. One of these per processed PDF."""

    merchant_name: Optional[str] = Field(None, description="Legal/DBA name of the merchant")
    statement_period: Optional[str] = Field(
        None, description="Billing period as printed, e.g. 'May 2024' or '05/01/24-05/31/24'"
    )
    total_volume: Optional[float] = Field(
        None, description="Total dollar volume processed (card sales) for the period"
    )
    transaction_count: Optional[int] = Field(
        None, description="Total number of transactions for the period"
    )
    total_fees: Optional[float] = Field(
        None, description="Total fees charged for the period (all-in)"
    )
    interchange_fees: Optional[float] = Field(
        None, description="Interchange paid to card-issuing banks (true cost)"
    )
    assessment_fees: Optional[float] = Field(
        None, description="Card-brand assessments/dues (true cost)"
    )
    processor_markup: Optional[float] = Field(
        None,
        description="Processor's markup above interchange + assessments "
        "(the Arch-addressable portion). Null if it can't be separated.",
    )
    fixed_fees: FixedFees = Field(default_factory=FixedFees)
    current_model: CurrentModel = Field(
        CurrentModel.UNKNOWN,
        description="Pricing model: flat, tiered, IC+ (interchange-plus), or unknown",
    )
    card_mix: Optional[list[CardMixEntry]] = Field(
        None, description="Per-card-type breakdown if the statement reports one"
    )
    notes: Optional[str] = Field(
        None,
        description="Anything unusual, ambiguous, or worth flagging "
        "(junk fees, missing data, assumptions made).",
    )


SYSTEM_PROMPT = """\
You are a payments analyst extracting structured data from a merchant credit-card \
processing statement. The text comes straight from a PDF and may be messy, \
out of order, or split across tables — statements vary a lot by processor \
(Fiserv, TSYS, Elavon, Paysafe, etc.).

Extract the requested fields accurately:
- Use dollar amounts as plain numbers (no $ or commas): 1234.56, not "$1,234.56".
- total_volume is card sales volume processed, not the total fees.
- Separate true cost (interchange + assessments) from processor_markup where the \
statement makes it possible. If the statement is flat/tiered and the markup can't \
be isolated, set processor_markup to null and say so in notes.
- If a value is genuinely not present on the statement, return null — do not guess \
or fabricate numbers.
- current_model: "IC+" if you see interchange passed through plus a markup; \
"tiered" for qualified/mid/non-qualified buckets; "flat" for a single blended rate; \
otherwise "unknown".
- Put anything ambiguous, any junk fees, or any assumptions you made in notes.
"""


def structure_statement(
    raw_text: str,
    *,
    model: str = DEFAULT_MODEL,
    client: anthropic.Anthropic | None = None,
) -> Statement:
    """Turn the raw statement blob into a validated `Statement`.

    Retries on malformed/refused output up to MAX_ATTEMPTS before giving up.
    """
    client = client or anthropic.Anthropic()

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.parse(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Extract the structured statement data from the raw "
                            "statement text below.\n\n"
                            "<statement>\n" + raw_text + "\n</statement>"
                        ),
                    }
                ],
                output_format=Statement,
            )

            if response.stop_reason == "refusal":
                raise RuntimeError(
                    "Model refused to process the statement "
                    f"(category: {getattr(response.stop_details, 'category', None)})."
                )

            parsed = response.parsed_output
            if parsed is None:
                raise ValueError("Model returned no parseable structured output.")
            return parsed

        except (anthropic.APIError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                continue

    raise RuntimeError(
        f"Failed to structure statement after {MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error
