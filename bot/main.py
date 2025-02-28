# Imports
import asyncio
import datetime
from dataclasses import dataclass
import re
from typing import Literal, Optional, Union


import discord
import os
from discord.ext import commands, tasks
from discord.utils import get

# User defined Imports
from .utils import common_member, unique


# Global Variables
global dayRegex, hourRegex, channelPreferences, messageReactions

dayRegex = re.compile(r"(\d+)[Dd]")
hourRegex = re.compile(r"(\d+)[Hh]")


@dataclass
class MessageReactionVote:
    message_id: str
    vote_count: int
    start_time: datetime.datetime
    duration: datetime.timedelta
    channel_id: str


messageReactions = dict()
# {"messageId":{"poritiveVoteEmoji":[array],"negativeVoteEmojiCount":[array],"startTime":datetime,"isEnded","channelID":"csdf",}}


@dataclass
class ChannelPreference:
    channel_id: str
    voting_method: Union[Literal["quorum"], Literal["time"]]
    time_for_vote: datetime.timedelta
    positive_vote_emoji: str
    roles_eligible: list[str]
    percent_to_clear: Optional[float] = None


MESSAGE_REACTIONS: list[MessageReaction] = []
CHANNEL_PREFERENCES: list[ChannelPreference] = []

channelPreferences = dict()
# {"channelID":{"votingMethod":("quorum","time"),"percentToClear/timeToVote":(33%/99hours),positiveVoteEmoji:"\emoji", negativeVoteEmoji:"\emoji2"},"rolesEligible":[all roles eligible]}


def hasTimePassed(startTime, interval):
    currTime = datetime.now()
    timeDiff = (currTime - startTime).total_seconds()
    interval = int(interval) * 60
    if timeDiff > interval:
        return True
    else:
        return False


async def embed(ctx):
    embed = discord.Embed(title="Channel Preferences")
    embed.add_field(
        name="Voting Method",
        value=channelPreferences[ctx.channel.id]["votingMethod"],
        inline=True,
    )
    embed.add_field(
        name="Positive Reactions",
        value=channelPreferences[ctx.channel.id]["positiveEmoji"],
    )
    embed.add_field(
        name="Negative Reactions",
        value=channelPreferences[ctx.channel.id]["negativeEmoji"],
    )
    if channelPreferences[ctx.channel.id]["votingMethod"] == "Quorum":
        embed.add_field(
            name="Win Percentage",
            value=channelPreferences[ctx.channel.id]["percentage"],
        )
    else:
        embed.add_field(
            name="Time",
            value=f'{channelPreferences[ctx.channel.id]["time"]//24} Days and {channelPreferences[ctx.channel.id]["time"]%24} Hours',
        )
    embed.add_field(
        name="Roles",
        value=[
            get(ctx.guild.roles, id=role_id).name
            for role_id in channelPreferences[ctx.channel.id]["roles"]
        ],
    )
    channelName = discord.utils.get(
        ctx.guild.channels, id=channelPreferences[ctx.channel.id]["resultChannel"]
    )
    embed.add_field(name="Result Channel", value=channelName)
    await ctx.send(embed=embed)


async def sendToChannel(preferenceObject, messageObject):
    channel = client.get_channel(preferenceObject["resultChannel"])
    currentChannel = client.get_channel(messageObject["channelID"])
    msg = await currentChannel.fetch_message(messageObject["messageID"])
    msgContent = msg.content

    embed = discord.Embed(title="Proposal results", description=msgContent)
    embed.add_field(
        name="Voting Method", value=preferenceObject["votingMethod"], inline=True
    )
    embed.add_field(name="In Favor", value=messageObject["positiveEmoji"])
    embed.add_field(name="Against", value=messageObject["negativeEmoji"])
    if messageObject["positiveEmoji"] > messageObject["negativeEmoji"]:
        result = "Passed"
    else:
        result = "Failed"
    embed.add_field(name="Result", value=result)
    memberCounts = totalMembers(currentChannel, preferenceObject["roles"])
    embed.add_field(name="Stats", value="Total Members and Votes by Role", inline=False)

    positiveReactions = [0 for a in preferenceObject["roles"]]

    negativeReactions = [0 for a in preferenceObject["roles"]]

    for currReaction in msg.reactions:
        if currReaction.emoji == preferenceObject["positiveEmoji"]:
            currReactionUser = await currReaction.users().flatten()
            for user in currReactionUser:
                user_roles = [role.id for role in user.roles]
                for i in range(len(preferenceObject["roles"])):
                    # We check what role does the user have
                    if preferenceObject["roles"][i] in user_roles:
                        positiveReactions[i] += 1
                        # based on the role, we can add a multiplier as well.
        if currReaction.emoji == preferenceObject["negativeEmoji"]:
            currReactionUser = await currReaction.users().flatten()
            for user in currReactionUser:
                user_roles = [role.id for role in user.roles]
                for i in range(len(preferenceObject["roles"])):
                    if preferenceObject["roles"][i] in user_roles:
                        negativeReactions[i] += 1

    for i in range(len(preferenceObject["roles"])):
        embed.add_field(
            name=get(currentChannel.guild.roles, id=preferenceObject["roles"][i]),
            value=memberCounts[i],
            inline=False,
        )
        embed.add_field(name="Voted Positive", value=positiveReactions[i], inline=True)
        embed.add_field(name="Voted Negative", value=negativeReactions[i], inline=True)
    await channel.send(embed=embed)


def members(ctx, roles):
    server = ctx.message.guild
    mems = []
    for role_id in roles:
        for member in server.members:
            member_role_ids = [role.id for role in member.roles]
            if role_id in member_role_ids:
                mems.append(member.id)
    uniquemems = unique(mems)
    count = len(uniquemems)
    return count


def reactionByRole(reaction, role):
    # for member in reaction.members:
    # if
    return True


def totalMembers(ctx, roles):
    server = ctx.guild
    mems = []

    for role_id in roles:
        roleCount = 0
        for member in server.members:
            member_role_ids = [role.id for role in member.roles]
            if role_id in member_role_ids:
                roleCount += 1
        mems.append(roleCount)
    return mems


intents = discord.Intents.default()
intents.members = True

client = commands.Bot(intents=intents, command_prefix="!")


@client.event
async def on_ready():
    print("we have logged in as{0.user}".format(client))


@client.command()
async def reset(ctx):
    global channelPreferences
    channelPreferences[ctx.channel.id] = {}
    return


@client.command()
async def sv(ctx):
    global dayRegex, hourRegex
    sentMessages = []
    if not ctx.author.guild_permissions.administrator:
        sentMessages.append(
            await ctx.channel.send("You need to be an Admin to access this role!")
        )
        return

    global channelPreferences
    currentPrefs = {}

    try:
        currentPrefs = channelPreferences[ctx.channel.id]
        sentMessages.append(
            await ctx.send("Let's Update Voting Preferences for this channel!")
        )

    except:
        currentPrefs = {}
        sentMessages.append(await ctx.send("Let's setup Voting for this channel!"))

    channelPreferences[ctx.channel.id] = currentPrefs

    sentMessages.append(await ctx.send("Select Q/q for Quorum or T/t for time"))

    def qtcheck(msg):
        return (
            msg.author == ctx.author
            and msg.channel == ctx.channel
            and msg.content.lower() in ["q", "t"]
        )

    msg_1 = await client.wait_for("message", check=qtcheck)
    sentMessages.append(msg_1)
    if msg_1.content.lower() == "q":
        sentMessages.append(await ctx.send("Quorum chosen, choose percentage!"))
        channelPreferences[ctx.channel.id]["votingMethod"] = "Quorum"
    elif msg_1.content.lower() == "t":
        sentMessages.append(await ctx.send("Time chosen, choose time!"))
        channelPreferences[ctx.channel.id]["votingMethod"] = "Time"
    else:
        await ctx.send("Invalid input")
        return

    def baseCheck(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    if channelPreferences[ctx.channel.id]["votingMethod"] == "Quorum":
        msg = await client.wait_for("message", check=baseCheck)
        sentMessages.append(msg)
        channelPreferences[ctx.channel.id]["percentage"] = msg.content
    elif channelPreferences[ctx.channel.id]["votingMethod"] == "Time":
        msg2 = await client.wait_for("message", check=baseCheck)
        hours = sum(int(h) for h in hourRegex.findall(msg2.content)) * 1
        days = sum(int(d) for d in dayRegex.findall(msg2.content)) * 24
        totalTime = hours + days
        sentMessages.append(msg2)
        channelPreferences[ctx.channel.id]["time"] = totalTime

    def checkEmoji(reaction, user):
        if (
            user == ctx.author
            and reaction.message.channel == ctx.channel
            and (
                (reaction.emoji != channelPreferences[ctx.channel.id]["positiveEmoji"])
                if "positiveEmoji" in channelPreferences[ctx.channel.id]
                else True
            )
        ):
            return True
        else:
            # await reaction.message.remove_reaction(reaction,user)
            # negativeMessage = await ctx.send("Don't set the same reaction you moron")
            # await asyncio.sleep(2)
            # await negativeMessage.delete();
            return False

    positiveMessage = await ctx.send("React with Positive Emoji!")
    positiveReaction, user = await client.wait_for("reaction_add", check=checkEmoji)
    channelPreferences[ctx.channel.id]["positiveEmoji"] = positiveReaction.emoji
    await asyncio.sleep(1)
    await positiveMessage.delete()
    negativeMessage = await ctx.send("React with Negative Emoji!")
    negativeReaction, user = await client.wait_for("reaction_add", check=checkEmoji)
    channelPreferences[ctx.channel.id]["negativeEmoji"] = negativeReaction.emoji
    await asyncio.sleep(1)
    await negativeMessage.delete()
    sentMessages.append(await ctx.send("Mention all Roles who can participate!"))
    msg3 = await client.wait_for("message", check=baseCheck)
    channelPreferences[ctx.channel.id]["roles"] = msg3.raw_role_mentions
    sentMessages.append(msg3)
    sentMessages.append(
        await ctx.send("Mention the Channel where you want the results")
    )
    msg4 = await client.wait_for("message", check=baseCheck)
    channelPreferences[ctx.channel.id]["resultChannel"] = msg4.channel_mentions[0].id
    sentMessages.append(msg4)
    await ctx.channel.delete_messages(sentMessages)
    await embed(ctx)
    channelPreferences[ctx.channel.id]["votingEnabled"] = True


@client.command()
async def gv(ctx):
    global channelPreferences
    await embed(ctx)


@client.event
async def on_message(message):
    global messageReactions, channelPreferences
    if message.author == client.user:
        return
    try:
        if "votingEnabled" not in channelPreferences[message.channel.id]:
            await client.process_commands(message)
            return
    except:
        await client.process_commands(message)
        return

    messageReactions[message.id] = dict()
    messageReactions[message.id]["startTime"] = datetime.now()
    messageReactions[message.id]["positiveEmoji"] = 0
    messageReactions[message.id]["negativeEmoji"] = 0
    messageReactions[message.id]["channelID"] = message.channel.id
    await message.add_reaction(channelPreferences[message.channel.id]["positiveEmoji"])
    await message.add_reaction(channelPreferences[message.channel.id]["negativeEmoji"])

    await client.process_commands(message)


@client.event
async def on_reaction_add(reaction, user):
    await on_reaction_change(reaction, user, "add")


@client.event
async def on_reaction_remove(reaction, user):
    await on_reaction_change(reaction, user, "remove")


async def on_reaction_change(reaction, user, action):
    if user == client.user:
        return
    global channelPreferences, messageReactions
    preference = {}
    try:
        preference = channelPreferences[reaction.message.channel.id]
        newLol = preference["roles"]
        messageChannel = messageReactions[reaction.message.id]

    except:
        return
    if "isEnded" in messageReactions[reaction.message.id]:
        await reaction.message.remove_reaction(reaction, user)
        return
    if preference["votingMethod"] == "Time":
        if "startTime" not in messageReactions[reaction.message.id]:

            messageReactions[reaction.message.id]["startTime"] = datetime.now()
        if hasTimePassed(
            messageReactions[reaction.message.id]["startTime"], preference["time"]
        ):

            messageReactions[reaction.message.id]["isEnded"] = True
            messageReactions[reaction.message.id]["messageID"] = reaction.message.id
            await sendToChannel(preference, messageReactions[reaction.message.id])
            await reaction.message.remove_reaction(reaction, user)
            return

    if not common_member(preference["roles"], [role.id for role in user.roles]):
        await reaction.message.remove_reaction(reaction, user)
        return
    if reaction.emoji == preference["positiveEmoji"]:
        if action == "add":
            await reaction.message.remove_reaction(preference["negativeEmoji"], user)
        # messageReactions[reaction.message.id]["positiveEmoji"]=reaction.count;

    elif reaction.emoji == preference["negativeEmoji"]:
        if action == "add":
            await reaction.message.remove_reaction(preference["positiveEmoji"], user)
        # messageReactions[reaction.message.id]["negativeEmoji"]=reaction.count;
    else:
        await reaction.message.remove_reaction(reaction, user)

    for cuRe in reaction.message.reactions:
        # -1 to remove bot's reaction
        if cuRe.emoji == preference["positiveEmoji"]:
            messageReactions[reaction.message.id]["positiveEmoji"] = cuRe.count - 1
        if cuRe.emoji == preference["negativeEmoji"]:
            messageReactions[reaction.message.id]["negativeEmoji"] = cuRe.count - 1

    if preference["votingMethod"] == "Quorum":
        # TODO Get total eligible Members
        totalEligibleMembers = max(1, members(reaction, preference["roles"]))
        positivePercent = (
            100
            * (messageReactions[reaction.message.id]["positiveEmoji"])
            / totalEligibleMembers
        )
        negativePercent = (
            100
            * (messageReactions[reaction.message.id]["negativeEmoji"])
            / totalEligibleMembers
        )

        preference["totalEligibleMembers"] = totalEligibleMembers
        preference["negativePercent"] = negativePercent

        if positivePercent >= int(preference["percentage"]) or negativePercent >= int(
            preference["percentage"]
        ):
            messageReactions[reaction.message.id]["messageID"] = reaction.message.id
            await sendToChannel(preference, messageReactions[reaction.message.id])
            messageReactions[reaction.message.id]["isEnded"] = True


@tasks.loop(seconds=1)
async def slow_count():
    await everyTwoHours()


slow_count.start()

# Tasks waala
async def everyTwoHours():
    try:
        global messageReactions, channelPreferences
        for messageID in messageReactions:
            if (
                "isEnded" in messageReactions[messageID]
                or "channelID" not in messageReactions[messageID]
                or "startTime" not in messageReactions[messageID]
            ):
                continue
            if (
                channelPreferences[messageReactions[messageID]["channelID"]][
                    "votingMethod"
                ]
                != "Time"
            ):
                continue

            if hasTimePassed(
                messageReactions[messageID]["startTime"],
                channelPreferences[messageReactions[messageID]["channelID"]]["time"],
            ):
                messageReactions[messageID]["isEnded"] = True
                messageReactions[messageID]["messageID"] = messageID

                await sendToChannel(
                    channelPreferences[messageReactions[messageID]["channelID"]],
                    messageReactions[messageID],
                )
    except Exception as e:
        print(e)


client.run(os.getenv("TOKEN"))
