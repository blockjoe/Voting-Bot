from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session


from .schemas import (
    Member,
    MemberBase,
    Status,
    Vote,
    VotesResponse,
    VouchEvent,
    VoteBase,
    VouchEventBase,
)
from .db import (
    Base,
    SessionLocal,
    engine,
    get_member_by_id,
    get_vote_by_id,
    get_current_votes,
    create_member,
    create_vote,
    create_vouch_event,
    delete_vouch_event,
    get_vouch_event_by_ids,
    complete_vote,
    get_existing_vote_by_discord_id,
)

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()


@app.get("/status", response_model=Status)
async def status():
    return Status()


@app.get("/members/{discord_id}", response_model=Member)
async def get_member(discord_id: str, db: Session = Depends(get_db)):
    db_member = get_member_by_id(db, discord_id)
    if db_member is None:
        raise HTTPException(
            status_code=400, detail="Member with id {} not found".format(discord_id)
        )
    return Member.from_orm(db_member)


@app.post("/members", response_model=Member)
async def add_member(member: MemberBase, db: Session = Depends(get_db)):
    db_member = get_member_by_id(db, member.discord_id)
    if db_member:
        raise HTTPException(
            status_code=400,
            detail="Member for {} already exists".format(member.discord_id),
        )
    db_member = create_member(db, member)
    return Member.from_orm(db_member)


@app.get("/votes/{message_id}", response_model=Vote)
async def get_vote(message_id: str, db: Session = Depends(get_db)):
    db_vote = get_vote_by_id(db, message_id)
    if db_vote is None:
        raise HTTPException(
            status_code=400,
            detail="Vote for message with id {} not found".format(message_id),
        )
    return Vote.from_orm(db_vote)


@app.get("/existing-votes/{discord_id}", response_model=Vote)
async def get_existing_vote(discord_id: str, db: Session = Depends(get_db)):
    db_vote = get_existing_vote_by_discord_id(db, discord_id)
    if db_vote is None:
        raise HTTPException(
            status_code=400,
            detail="No existing votes found for {}".format(discord_id),
        )
    return Vote.from_orm(db_vote)


@app.post("/votes", response_model=Vote)
async def add_vote(vote: VoteBase, db: Session = Depends(get_db)):
    db_vote = create_vote(db, vote)
    return Vote.from_orm(db_vote)


@app.get("/outstanding-votes", response_model=VotesResponse)
async def get_outstanding_votes(db: Session = Depends(get_db)):
    votes = get_current_votes(db)
    for vote in votes:
        if vote.failed:
            complete_vote(db, vote)
    return {"votes": [Vote.from_orm(vote) for vote in votes]}


@app.post("/vouches", response_model=VouchEvent)
async def get_vouch_event(vouch: VouchEventBase, db: Session = Depends(get_db)):
    vouch_db = get_vouch_event_by_ids(db, vouch)
    if vouch_db is None:
        raise HTTPException(
            status_code=400,
            detail="No vouch event found for: message='{}' voucher='{}'".format(
                vouch.vote_id, vouch.voucher_id
            ),
        )
    return VouchEvent.from_orm(vouch_db)


@app.post("/vouch-event", response_model=VouchEvent)
async def add_vouch_event(vouch: VouchEventBase, db: Session = Depends(get_db)):
    vouch_db = create_vouch_event(db, vouch)
    print(vouch_db.vote.votes, vouch_db.vote.successful)
    if vouch_db.vote.successful:
        complete_vote(db, vouch_db.vote)
    return VouchEvent.from_orm(vouch_db)


@app.post("/vouch-event/delete", response_model=Status)
async def remove_vouch_event(vouch: VouchEventBase, db: Session = Depends(get_db)):
    status = delete_vouch_event(db, vouch)
    if status:
        return Status(alive=status)
    raise HTTPException(
        status_code=400,
        detail="No vouch event found for: message='{}' voucher='{}'".format(
            vouch.vote_id, vouch.voucher_id
        ),
    )
