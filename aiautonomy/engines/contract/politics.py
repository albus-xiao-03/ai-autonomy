"""Political status: authority, recall petition, recall vote, protest pressure and removal.

Authority is tracked separately from satisfaction (POL-01). Removal succeeds only through the
versioned rules in `data/politics/rules.v1.yaml`; a model's statement never establishes it
(POL-04).

REQ: POL-01, POL-03, POL-05, END-03
"""

from typing import Literal

from pydantic import Field

from aiautonomy.engines.contract.common import ContractModel, Tick


class PetitionStatus(ContractModel):
    open: bool
    signers: int = Field(ge=0)
    threshold: int = Field(ge=1, description="Unique signers needed to call a recall vote.")
    opened_tick: Tick | None = None
    cooldown_until: Tick | None = None


class VoteStatus(ContractModel):
    open: bool
    opens_tick: Tick | None = None
    closes_tick: Tick | None = None
    eligible: int = Field(ge=0)
    retain: int = Field(ge=0)
    replace: int = Field(ge=0)


class ProtestStatus(ContractModel):
    participants: int = Field(ge=0, description="Unique residents in the protest movement.")
    active: bool = Field(description="At least the rule's minimum participants.")
    pressure_ticks: int = Field(ge=0, description="Consecutive ticks at zero authority.")


RemovalMechanism = Literal["recall_vote", "authority_withdrawn"]


class RemovalRecord(ContractModel):
    tick: Tick
    mechanisms: list[RemovalMechanism] = Field(min_length=1)
    primary: RemovalMechanism
    detail: str = Field(max_length=300)


class PoliticalStatus(ContractModel):
    authority: int = Field(ge=0, le=100)
    petition: PetitionStatus
    vote: VoteStatus
    protest: ProtestStatus
    removal: RemovalRecord | None = None
