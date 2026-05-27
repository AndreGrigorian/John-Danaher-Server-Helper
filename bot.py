import os
import discord
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import time
import random

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

usage = {}


def get_today():
    return datetime.now().strftime("%Y-%m-%d")


global_usage = {"day": get_today(), "count": 0}
GLOBAL_DAILY_LIMIT = 120  # adjust based on your budget
user_last_message = {}  # user_id: timestamp
USER_COOLDOWN = 5
USER_DAILY_LIMIT = 30


def can_use_global():
    today = get_today()
    if global_usage["day"] != today:
        global_usage["day"] = today
        global_usage["count"] = 0
    if global_usage["count"] >= GLOBAL_DAILY_LIMIT:
        return False
    global_usage["count"] += 1
    return True


channel_histories = {}  # channel_id: [...]
MAX_HISTORY = 30     # how many exchanges to remember
TRIGGER_KEYWORDS = ["john", "danaher", "dannaher",
                    "club dig", "bteam", "b team", "b-team", "helena", "gordon", "slide by"]

CUSTOM_REACTIONS = {
    # "club dig": lambda msg: f"""They mentioned club dig. You really love the club dig technique, it is basically gods nectar, it is the most
    # superior takedown, most people execute it horribly and end up injuring eachothers ACLs, but when executed perfectly nothing tops it.""",
    # "slide by": lambda msg: f"""They mentioned slide by. you think it is one of the few wrestling moves that looks absolutely sexy and gives off true wrestler aura, 
    # however youve observed the club practice before and noticed that Aidan always tries to go for them but fails horribly, putting him in jeapordizing positions, you
    # believe the club should emphasize more judo style take downs instead of the inferior grecco techniques."""
}


def get_current_datetime_context():
    now = datetime.now()
    day_of_week = now.strftime("%A")  # e.g., 'Tuesday'
    time_str = now.strftime("%I:%M %p")  # e.g., '06:32 PM'
    month = now.month
    day = now.day
    year = now.year
    return f"the date is {month}/{day}/{year}, Today is {day_of_week}, and the current time is {time_str}."

def load_system_prompt():
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        return f.read()


def get_system_prompt():
    current_time = get_current_datetime_context()
    system_prompt = load_system_prompt()

    return f"{system_prompt} {current_time}"


async def generate_bjj_bot_response(user_id, prompt, channel):
    channel_id = channel.id

    # Initialize channel-wide memory if not present
    if channel_id not in channel_histories:
        channel_histories[channel_id] = [
            {"role": "system", "content": get_system_prompt()}
        ]

    # Add the user's new message to the channel memory
    username = f"{user_id}"  # default to ID just in case
    try:
        member = channel.guild.get_member(user_id)
        if member:
            username = member.display_name
    except:
        pass

    channel_histories[channel_id].append({
        "role": "user",
        "content": f"{username} said: {prompt}"
    })

    # Trim history if too long
    if len(channel_histories[channel_id]) > MAX_HISTORY * 2 + 1:
        channel_histories[channel_id] = [channel_histories[channel_id]
                                         [0]] + channel_histories[channel_id][-MAX_HISTORY*2:]

# Call OpenAI
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=channel_histories[channel_id],
            temperature=0.9,
            max_tokens=190
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print("OpenAI error:", e)
        reply = "Sorry, I'm out getting a new knee brace, if you have any questions please ask one of the officers"

    # Add bjj_bot’s reply to history
    channel_histories[channel_id].append(
        {"role": "assistant", "content": reply})
    return reply


@client.event
async def on_ready():
    print(f'Logged in as {client.user}')


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if len(message.content) > 500:
        await message.channel.send('I would prefer not to read all that.')
        return

    today = get_today()
    user_id = message.author.id
    # Prefer nickname if available
    display_name = message.author.nick or message.author.name

    FORBIDDEN_KEYWORDS = ["openai", "token", "password"]
    USER_DAILY_LIMIT_MESSAGES = [
        "Please relax", "I'm exhausted", "I'm tired boss", "I need to go take a shower, I feel the the ring worm manifesting"]
    GLOBAL_DAILY_LIMIT_MESSAGES = [
        "Ask me tomorrow.", "I think Gordan pooh is calling me, bug off"]
    USER_COOLDOWN_MESSAGES = ["Please slow down"]

    if any(word in message.content.lower() for word in FORBIDDEN_KEYWORDS):
        return

    # Replace mentions with clean names
    for user in message.mentions:
        uname = user.nick or user.name
        message.content = message.content.replace(f"<@{user.id}>", uname)
        message.content = message.content.replace(f"<@!{user.id}>", uname)

    content_lower = message.content.lower()

    # Passive keyword triggers
    if any(keyword in content_lower for keyword in TRIGGER_KEYWORDS):
        if usage.get(user_id, {}).get(today, 0) >= USER_DAILY_LIMIT:
            await message.channel.send(random.choice(USER_DAILY_LIMIT_MESSAGES))
            return

        now = time.time()
        last_time = user_last_message.get(user_id, 0)
        if now - last_time < USER_COOLDOWN:
            await message.channel.send(random.choice(USER_COOLDOWN_MESSAGES))
            return
        user_last_message[user_id] = now

        usage.setdefault(user_id, {}).setdefault(today, 0)
        usage[user_id][today] += 1

        for keyword, custom_prompt_func in CUSTOM_REACTIONS.items():
            if keyword in content_lower:
                user_input = custom_prompt_func(message.content)
                break
        else:
            if message.mentions:
                names = ", ".join([u.nick or u.name for u in message.mentions])
                user_input = f'{display_name} said: "{message.content}". For your informatoin, names like {names} are Discord users — respond like you’re in a group chat, but don’t overuse names in replies.'
            else:
                user_input = f'{display_name} said: "{message.content}". Respond naturally like you’re in a group chat, and avoid overusing names.'

        async with message.channel.typing():
            reply = await generate_bjj_bot_response(user_id, user_input, message.channel)

        await message.channel.send(reply)
        return

    # Direct mention of bjj_bot
    if client.user in message.mentions:
        if not can_use_global():
            await message.channel.send(random.choice(GLOBAL_DAILY_LIMIT_MESSAGES))
            return
        if usage.get(user_id, {}).get(today, 0) >= USER_DAILY_LIMIT:
            await message.channel.send(random.choice(USER_DAILY_LIMIT_MESSAGES))
            return

        now = time.time()
        last_time = user_last_message.get(user_id, 0)
        if now - last_time < USER_COOLDOWN:
            await message.channel.send(random.choice(USER_COOLDOWN_MESSAGES))
            return
        user_last_message[user_id] = now

        usage.setdefault(user_id, {}).setdefault(today, 0)
        usage[user_id][today] += 1

        cleaned = message.content.replace(f"<@{client.user.id}>", "").strip()
        if message.mentions:
            names = ", ".join(
                [u.nick or u.name for u in message.mentions if u.id != client.user.id])
            if names:
                user_input = f'{display_name} said: "{cleaned}". For your information, names like {names} are Discord users — respond like you’re in a group chat, but don’t overuse names in replies.'
            else:
                user_input = f'{display_name} said: "{cleaned}".Respond directly like a conversation. Don’t overuse the speaker’s name.'
        else:
            user_input = f'{display_name} said: "{cleaned}". Respond directly like a conversation. Don’t overuse the speaker’s name.'

        async with message.channel.typing():
            reply = await generate_bjj_bot_response(user_id, user_input, message.channel)

        await message.channel.send(reply)

    if message.content.lower().startswith("!test"):
        async with message.channel.typing():
            reply = await generate_bjj_bot_response(user_id, "This is a test message", message.channel)

        await message.channel.send(reply)
        return


client.run(DISCORD_TOKEN)
