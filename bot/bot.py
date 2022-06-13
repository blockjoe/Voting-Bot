import datetime
import os
from typing import List

import aiohttp
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv

from .schemas import (
    Status,
    MemberBase,
    VoteBase,
    Vote,
    VouchEventBase,
    VouchEvent,
    VotesResponse,
)

intents = discord.Intents.all()
client = commands.Bot(command_prefix="!", intents=intents)

EXISTING_VOTER_ROLE_NAME = "Voter"
VOUCHER_ROLE = "Verified"
CAN_CALL_VERIFY_ROLE = "Trophied"
VOUCHING_CHANNELS = [984295827868631060]
VOTE_REACT = "✅"
VOTE_PERCENT = 0.33
VOTE_DAYS = 7


def in_vouching_channel(message: discord.Message) -> bool:
    return message.channel.id in VOUCHING_CHANNELS


def is_voter(user: discord.Member) -> bool:
    return EXISTING_VOTER_ROLE_NAME in [role.name for role in user.roles]


def is_vouched_for(user: discord.Member) -> bool:
    return VOUCHER_ROLE in [role.name for role in user.roles]


async def get_voters(ctx) -> List[discord.Member]:
    return [
        member
        for member in ctx.guild.members
        if EXISTING_VOTER_ROLE_NAME in [role.name for role in member.roles]
    ]


async def send_not_authorized_to_vote_reply(
    reaction: discord.Reaction, user: discord.Member
):
    await reaction.message.reply(
        "The vote cast by {} was removed as they don't have the Voter Role. Only Voters can verify community members.".format(
            user.display_name
        )
    )


async def send_vouch_sucessful_reply(
    member_id: str, message: discord.Message, votes: int
):
    member = await message.guild.fetch_member(int(member_id))
    await message.reply(
        "{} was successfully verified! They received {} approvals and are now one step closer to become a Voter...".format(
            member.display_name, votes
        )
    )
    role = discord.utils.get(message.guild.roles, name=VOUCHER_ROLE)
    await member.add_roles(role)


async def send_vouch_failed_reply(vote: Vote):
    channel = client.get_channel(VOUCHING_CHANNELS[0])
    vote_message = await channel.fetch_message(vote.message_id)
    await vote_message.reply(
        "{} has failed verification. Only {} of the needed {} votes after {} days.".format(
            vote.on_behalf_of.discord_name,
            vote.votes,
            vote.vouches_required,
            vote.days,
        )
    )


async def send_already_vouched_for_reply(ctx: Context):
    await ctx.reply(
        "You have already been verified, {}.".format(ctx.author.display_name)
    )


async def send_vote_exists_message(vote: discord.Message):
    await vote.reply(
        "Your verification vote is already in progress, {}.".format(
            vote.author.display_name
        )
    )


async def send_vote_embed(
    ctx: Context, votes_needed: int, votes_total: int
) -> discord.Message:
    embed = discord.Embed(
        title="{} is seeking community verification.".format(ctx.author.display_name)
    )
    embed.description = "Approval is needed from {} of {} available voters in the next {} days. Voters, only click the {} if they have posted a selfie and filled out the required template for verification. Votes cast by anyone without the Voter role will be removed.".format(
        votes_needed, votes_total, VOTE_DAYS, VOTE_REACT
    )
    vote = await ctx.reply(embed=embed)
    await vote.add_reaction(VOTE_REACT)
    return vote


async def attempt_to_add_user(user: discord.Member):
    member = MemberBase(
        discord_id=user.id,
        discord_name=user.display_name,
        is_vouched_for=is_vouched_for(user),
        is_voter=is_voter(user),
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/members",
            json=member.dict(),
            headers={"Content-Type": "application/json"},
        ) as resp:
            response = await resp.json()
            return response


async def attempt_to_start_vote(ctx: Context):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://localhost:8000/existing-votes/{}".format(ctx.author.id),
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status == 200:
                vote = await resp.json()
                vote_msg = await ctx.channel.fetch_message(vote["message_id"])
                await send_vote_exists_message(vote_msg)
                return

        voters = await get_voters(ctx)
        n_voters = len(voters)
        votes_needed = max(1, int(VOTE_PERCENT * n_voters))
        vote_message = await send_vote_embed(ctx, votes_needed, n_voters)
        vote = VoteBase(
            message_id=str(vote_message.id),
            on_behalf_of_id=ctx.author.id,
            start_time=datetime.datetime.utcnow(),
            days=VOTE_DAYS,
            vouches_required=votes_needed,
        )
        async with session.post(
            "http://localhost:8000/votes",
            json=vote.dict(),
            headers={"Content-Type": "application/json"},
        ) as resp:
            await resp.json()


def is_vote_reaction(reaction: discord.Reaction) -> bool:
    return reaction.emoji == VOTE_REACT


async def is_message_active_vote(message: discord.Message) -> bool:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://localhost:8000/votes/{}".format(message.id),
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                return False
            vote = await resp.json()
            return not vote["complete"]


async def send_vouch_event(reaction: discord.Reaction, user: discord.Member):
    vouch = VouchEventBase(vote_id=reaction.message.id, voucher_id=user.id)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/vouch-event",
            json=vouch.dict(),
            headers={"Content-Type": "application/json"},
        ) as resp:
            vouch_data = await resp.json()
            vouch = VouchEvent(**vouch_data)
            if vouch.vote.complete:
                await send_vouch_sucessful_reply(
                    vouch.vote.on_behalf_of_id, reaction.message, vouch.vote.votes
                )


async def send_vouch_revoked_event(reaction: discord.Reaction, user: discord.Member):
    vouch = VouchEventBase(vote_id=reaction.message.id, voucher_id=user.id)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/vouch-event/delete",
            json=vouch.dict(),
            headers={"Content-Type": "application/json"},
        ) as resp:
            status = await resp.json()


@client.event
async def on_ready():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/status") as resp:
            data = await resp.json()
            status = Status(**data)
            print("Backend online: {}".format(status.alive))


@client.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.Member):
    if not in_vouching_channel(reaction.message):
        return
    if user == client.user:
        return
    is_vote = await is_message_active_vote(reaction.message)
    if is_vote:
        if not is_vote_reaction(reaction):
            return
        if not is_voter(user):
            await reaction.message.remove_reaction(reaction, user)
            await send_not_authorized_to_vote_reply(reaction, user)
            return
        await send_vouch_event(reaction, user)
    await attempt_to_add_user(user)


@client.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.Member):
    if not in_vouching_channel(reaction.message):
        return
    if user == client.user:
        return
    is_vote = await is_message_active_vote(reaction.message)
    if is_vote:
        if not is_voter(user):
            return
        if not is_vote_reaction(reaction):
            return
        await send_vouch_revoked_event(reaction, user)
    await attempt_to_add_user(user)


@client.command(name="verify")
async def verify(ctx: Context):
    if not in_vouching_channel(ctx.message):
        return
    if is_vouched_for(ctx.author):
        await send_already_vouched_for_reply(ctx)
        return
    await attempt_to_add_user(ctx.author)
    await attempt_to_start_vote(ctx)


@tasks.loop(minutes=10)
async def sweep_outstanding_votes():
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://localhost:8000/outstanding-votes",
            headers={"Content-Type": "application/json"},
        ) as resp:
            response = await resp.json()
            votes = VotesResponse(**response.dict()).votes
            for vote in votes:
                if vote.complete:
                    await send_vouch_failed_reply(vote)


def main():
    load_dotenv()
    client.run(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    main()
