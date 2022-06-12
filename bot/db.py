import datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .schemas import MemberBase, VoteBase, VouchEventBase

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Member(Base):

    __tablename__ = "members"

    discord_id = Column(String, primary_key=True, index=True)
    discord_name = Column(String, nullable=False)
    discord_pp_url = Column(String)
    is_vouched_for = Column(Boolean)
    is_voter = Column(Boolean)

    votes = relationship("Vote", back_populates="on_behalf_of")


class Vote(Base):

    __tablename__ = "vouch_votes"

    message_id = Column(String, primary_key=True, index=True)
    on_behalf_of_id = Column(String, ForeignKey("members.discord_id"))
    message_text = Column(String)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    vouches_required = Column(Integer, nullable=False)
    votes = Column(Integer)
    complete = Column(Boolean)

    on_behalf_of = relationship("Member", back_populates="votes")
    vouches = relationship("Vouch", back_populates="vote")

    @property
    def failed(self):
        return (
            self.votes < self.vouches_required
            and self.end_time < datetime.datetime.utcnow()
        )

    @property
    def successful(self):
        return self.votes >= self.vouches_required and (
            self.end_time >= datetime.datetime.utcnow() or self.complete
        )


class Vouch(Base):

    __tablename__ = "vouches"

    vouch_id = Column(Integer, primary_key=True)
    vote_id = Column(String, ForeignKey("vouch_votes.message_id"))
    voucher_id = Column(String, ForeignKey("members.discord_id"))

    vote = relationship("Vote", back_populates="vouches")


def get_member_by_id(db, id_: str):
    return db.query(Member).filter(Member.discord_id == id_).first()


def get_vote_by_id(db, id_: str):
    return db.query(Vote).filter(Vote.message_id == id_).first()


def create_member(db, member: MemberBase):
    db_member = Member(**member.dict())
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    return db_member


def create_vote(db, vote: VoteBase):
    vote_dict = vote.dict(as_datetime=True, exclude={"days"})
    vote_dict["end_time"] = vote.end_time
    vote_dict["complete"] = False
    db_vote = Vote(**vote_dict)
    db.add(db_vote)
    db.commit()
    db.refresh(db_vote)
    return db_vote


def get_existing_vote_by_discord_id(db, discord_id: str):
    return (
        db.query(Vote)
        .filter(
            Vote.on_behalf_of_id == discord_id
            and Vote.end_time > datetime.datetime.utcnow()
        )
        .first()
    )


def get_vouch_event_by_ids(db, vouch: VouchEventBase):
    return (
        db.query(Vouch)
        .filter(Vouch.vote_id == vouch.vote_id and Vouch.voucher_id == vouch.voucher_id)
        .first()
    )


def delete_vouch_event(db, vouch: VouchEventBase):
    db_vouch = get_vouch_event_by_ids(db, vouch)
    if db_vouch:
        db_vote = get_vote_by_id(db, db_vouch.vote.message_id)
        db_vote.votes -= 1
        db.delete(db_vouch)
        db.commit()
        return True
    return False


def create_vouch_event(db, vouch: VouchEventBase):
    db_vouch = Vouch(**vouch.dict())
    db_vote = get_vote_by_id(db, db_vouch.vote.message_id)
    db_vote.votes += 1
    db.add(db_vouch)
    db.commit()
    db.refresh(db_vouch)
    return db_vouch


def get_current_votes(db):
    return db.query(Vote).filter(Vote.complete != True).all()


def complete_vote(db, vote: Vote):
    vote.complete = True
    db.commit()
    db.refresh(vote)
    return vote
