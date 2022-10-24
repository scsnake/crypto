from requests import Session
from bs4 import BeautifulSoup as bs
from contextlib import suppress
import traceback, os
from dotenv import load_dotenv
from discord_bot import user_send_msg
from time import sleep
from discord.ext import commands, tasks
from discord import Intents

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
PASSWORD = os.getenv('PW')
AUTH = os.getenv('USER_TOKEN')

intents = Intents.default()
intents.message_content = True
client = bot = commands.Bot(command_prefix='/', intents=intents)
client_channels = dict()


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if guild.name == GUILD:
            try:
                for ch in client.get_all_channels():
                    if ch.name == 'other-notify':
                        client_channels[ch.name] = ch
                        break
                        # await ch.send(ch.name)
            except Exception as e:
                print(e)
                pass

            print(
                f'{bot.user} is connected to the following guild:\n'
                f'{guild.name}(id: {guild.id})'
            )

            check_opensea.start()

            break


@tasks.loop(seconds=5)
async def check_opensea():
    global last_fp, fp
    for collection in collections_to_follow:
        c = get_collection(collection)
        try:
            fp = c['collection']['stats']['floor_price']
            fp = float(fp)
        except:
            traceback.print_exc()
        last_fp = floor_prices[collection]
        if last_fp != 0 and last_fp != fp:
            await notify_discord('fp {} https://opensea.io/collection/{}'.format(
                fp, collection
            ))
        floor_prices[collection] = fp


def get_collection(collection):
    url = 'https://api.opensea.io/api/v1/collection/{}'.format(collection)
    res = s.get(url)
    try:
        ret = res.json()
        return ret
    except:
        traceback.print_exc()


async def notify_discord(msg):
    await client_channels['other-notify'].send(msg)
    # ret = user_send_msg(notify_discord_channel, msg, AUTH)
    # return ret

if __name__ == '__main__':
    # notify_discord('test')

    collections_to_follow = ['mirai-rs']
    s = Session()

    floor_prices = {c: 0 for c in collections_to_follow}
    client.run(TOKEN)

