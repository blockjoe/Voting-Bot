import datetime
import os

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import Context
from dotenv import load_dotenv

from .schemas import Status, MemberBase, VoteBase, VouchEventBase, VouchEvent

intents = discord.Intents.all()
client = commands.Bot(command_prefix="!", intents=intents)

EXISTING_VOTER_ROLE_NAME = "Voter"
VOUCHER_ROLE = "VouchedFor"
VOUCHING_CHANNELS = [984952580130111498]
VOTE_REACT = "✅"
VOTE_DAYS = 7
VOTE_PERCENT = 0.33


def in_vouching_channel(message: discord.Message) -> bool:
    return message.channel.id in VOUCHING_CHANNELS


def is_voter(user: discord.Member) -> bool:
    return EXISTING_VOTER_ROLE_NAME in [role.name for role in user.roles]


def is_vouched_for(user: discord.Member) -> bool:
    return VOUCHER_ROLE in [role.name for role in user.roles]


async def get_voters(ctx) -> list[discord.Member]:
    return [
        member
        for member in ctx.guild.members
        if EXISTING_VOTER_ROLE_NAME in [role.name for role in member.roles]
    ]


async def send_not_authorized_to_vote_embed(
    reaction: discord.Reaction, user: discord.Member
):
    embed = discord.Embed(title="Unauthroized vote removed")
    embed.description = (
        "The vote cast by {} was removed as they don't have the Voter Role".format(
            user.display_name
        )
    )
    await reaction.message.reply(embed=embed)


async def send_already_vouched_for_embed(ctx: Context):
    embed = discord.Embed(
        title="{} is already vouched for".format(ctx.author.display_name)
    )
    embed.description = "You have already been vouched for, no need to start a vote."
    await ctx.send(embed=embed)


async def send_vote_exists_message(vote: discord.Message):
    await vote.reply("Verification vote is already in progress.")


async def send_vote_embed(
    ctx: Context, votes_needed: int, votes_total: int
) -> discord.Message:
    embed = discord.Embed(
        title="{} is seeking community verfication.".format(ctx.author.display_name)
    )
    embed.description = "Approval is needed from {} of {} available voters.".format(
        votes_needed, votes_total
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
        votes_needed = int(VOTE_PERCENT * n_voters)
        vote_message = await send_vote_embed(ctx, votes_needed, n_voters)
        vote = VoteBase(
            message_id=vote_message.id,
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
            return not vote.complete


async def send_vouch_sucessful(member_id: str, message: discord.Message):
    member = message.server.get_member(int(member_id))
    embed = discord.Embed(
        title="Community Verification Successful for {}".format(member.display_name)
    )
    await message.reply(embed=embed)


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
                await send_vouch_sucessful(vouch.vote.on_behalf_of_id, reaction.message)


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
            await send_not_authorized_to_vote_embed(reaction, user)
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
        if not is_vote_reaction(reaction):
            return
        await send_vouch_revoked_event(reaction, user)
    await attempt_to_add_user(user)


@client.command(name="verify")
async def verify(ctx: Context):
    if not in_vouching_channel(ctx.message):
        return
    if is_vouched_for(ctx.author) or is_voter(ctx.author):
        await send_already_vouched_for_embed(ctx)
    await attempt_to_add_user(ctx.author)
    await attempt_to_start_vote(ctx)


load_dotenv()
client.run(os.getenv("DISCORD_TOKEN"))
