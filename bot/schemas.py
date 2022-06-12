import datetime
from typing import Optional
from pydantic import BaseSettings, BaseModel, validator


class VouchConfiguration(BaseSettings):

    vouch_percentage_needed: float = 0.33
    vouch_attempts_allowed: int = 3
    vouch_attempt_cooldown: datetime.timedelta = datetime.timedelta(days=7)
    vouch_duration: datetime.timedelta = datetime.timedelta(days=7)
    in_channels: list[str]
    vouched_for_role: str
    voter_role: str


class MemberBase(BaseModel):
    discord_id: str
    discord_name: str
    is_vouched_for: bool = False
    is_voter: bool = False

    @classmethod
    def from_orm(cls, db_model):
        return cls(
            discord_id=db_model.discord_id,
            discord_name=db_model.discord_name,
            is_vouched_for=db_model.is_vouched_for,
            is_voter=db_model.is_voter,
        )


class VoteBase(BaseModel):
    message_id: str
    on_behalf_of_id: str
    start_time: datetime.datetime
    days: int
    vouches_required: int
    votes: int = 0
    complete: bool = False
    message_text: Optional[str] = None

    @validator("start_time", pre=True)
    def to_datetime(cls, v):
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            return datetime.datetime.fromisoformat(v)
        return v

    @property
    def duration(self):
        return datetime.timedelta(days=self.days)

    @property
    def end_time(self):
        return self.start_time + self.duration

    @classmethod
    def from_orm(cls, db_model):
        return cls(
            message_id=db_model.message_id,
            on_behalf_of_id=db_model.on_behalf_of_id,
            start_time=db_model.start_time,
            days=(db_model.end_time - db_model.start_time).days,
            vouches_required=db_model.vouches_required,
            message_text=db_model.message_text,
            complete=db_model.complete,
        )

    def dict(self, as_datetime=False, **kwargs):
        output = super().dict(**kwargs)
        for k, v in output.items():
            if isinstance(v, datetime.datetime) and not as_datetime:
                # datetime: "2022-04-16T06:43:56+00:00"
                output[k] = v.isoformat()
        return output


class VouchEventBase(BaseModel):
    vote_id: str
    voucher_id: str

    @classmethod
    def from_orm(cls, db_model):
        return cls(
            vote_id=db_model.vote_id,
            voucher_id=db_model.voucher_id,
        )


class Vote(VoteBase):
    on_behalf_of: MemberBase
    vouches: list[VouchEventBase]

    @classmethod
    def from_orm(cls, db_model):
        on_behalf_of_db = db_model.on_behalf_of
        vouches_db = db_model.vouches
        on_behalf_of = MemberBase.from_orm(on_behalf_of_db)
        vouches = [VouchEventBase.from_orm(vouch) for vouch in vouches_db]
        return cls(
            message_id=db_model.message_id,
            on_behalf_of_id=db_model.on_behalf_of_id,
            start_time=db_model.start_time,
            days=(db_model.end_time - db_model.start_time).days,
            vouches_required=db_model.vouches_required,
            message_text=db_model.message_text,
            complete=db_model.complete,
            on_behalf_of=on_behalf_of,
            vouches=vouches,
        )


class VouchEvent(VouchEventBase):
    vote: VoteBase

    @classmethod
    def from_orm(cls, db_model):
        return cls(
            vote_id=db_model.vote_id,
            voucher_id=db_model.voucher_id,
            vote=VoteBase.from_orm(db_model.vote),
        )


class Member(MemberBase):
    votes: list[Vote]

    @classmethod
    def from_orm(cls, db_model):
        return cls(
            discord_id=db_model.discord_id,
            discord_name=db_model.discord_name,
            is_vouched_for=db_model.is_vouched_for,
            is_voter=db_model.is_voter,
            votes=[Vote.from_orm(vote) for vote in db_model.votes],
        )


class Status(BaseModel):
    alive: bool = True


class VotesResponse(BaseModel):
    votes: list[Vote]
