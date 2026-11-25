from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, field_validator

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class OpenRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Code
    jig: Code
    current_profile: Code
    candidate_profile: Code
    target_count: int = Field(ge=1, le=20)


class BookOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: Code
    # 单据编号可空，留空时由服务端生成
    code: Code | None = None
    heat: FiniteFloat
    thick: FiniteFloat
    target: FiniteFloat

    @field_validator('code', mode='before')
    @classmethod
    def blank_as_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SignOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: Code
    measured: FiniteFloat
