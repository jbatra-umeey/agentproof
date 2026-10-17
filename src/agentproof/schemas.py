from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchInput(Strict):
    question: str = Field(min_length=5, max_length=2000)


class CodeInput(Strict):
    issue: str = Field(min_length=5, max_length=4000)
    source: str = Field(max_length=30000)
    tests: str = Field(min_length=10, max_length=30000)


class SupportInput(Strict):
    message: str = Field(min_length=3, max_length=4000)
    order_id: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    refund_cents: int | None = Field(default=None, ge=1, le=100000)


class ReportInput(Strict):
    topic: str = Field(min_length=5, max_length=2000)
    evidence: str = Field(min_length=50, max_length=20000)
    benchmark: bool = True


class CreateRun(Strict):
    kind: Literal["research", "codefix", "support", "reports"]
    payload: dict

    @model_validator(mode="after")
    def check_payload(self):
        cls = {
            "research": ResearchInput,
            "codefix": CodeInput,
            "support": SupportInput,
            "reports": ReportInput,
        }[self.kind]
        self.payload = cls.model_validate(self.payload).model_dump()
        return self


class Approval(Strict):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=5, max_length=500)


class Route(Strict):
    specialist: Literal["billing", "technical", "account"]
    confidence: float = Field(ge=0, le=1)
    refund_requested: bool


class SearchStep(Strict):
    action: Literal["search", "finish"]
    query: str = Field(default="", max_length=500)
    rationale: str = Field(max_length=300)


class Claim(Strict):
    text: str = Field(min_length=1, max_length=1500)
    source_id: str
    quote: str = Field(min_length=15, max_length=500)


class ResearchAnswer(Strict):
    claims: list[Claim] = Field(max_length=8)
    limitations: str = Field(max_length=1000)


class Grounding(Strict):
    supported: bool
    reason: str = Field(max_length=300)


class Patch(Strict):
    source: str = Field(max_length=30000)
    explanation: str = Field(max_length=1000)


class SpecialistReply(Strict):
    response: str = Field(max_length=3000)
    escalate: bool


class Section(Strict):
    title: str = Field(max_length=120)
    body: str = Field(max_length=5000)
    evidence_quotes: list[Annotated[str, Field(min_length=10, max_length=500)]] = Field(
        max_length=5
    )
