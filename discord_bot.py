import requests
import json
import random
import time
import traceback
import pandas as pd
from pathlib import Path
from threading import Timer, Thread, Lock
import re
from time import sleep, time
from datetime import datetime
from typing import Literal
from queue import Queue
from collections import deque
import asyncio
import os
from urllib.parse import quote
from contextlib import suppress

import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
from discord import Intents
import concurrent.futures
from functools import partial

# from discord_slash import SlashCommand, SlashContext
# from discord_slash.utils.manage_commands import create_choice, create_option

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
PASSWORD = os.getenv('PW')
AUTH = os.getenv('USER_TOKEN')

intents = Intents.default()
intents.message_content = True

# intents = discord.Intents(messages=True, guilds=True)

client = bot = commands.Bot(command_prefix='/', intents=intents)
client_channels = dict()
channel_types = 'announcement,giveaway,game'.split(',')
# msg_to_be_sent = {c: Queue() for c in channel_types}

lock = Lock()
rumble_msg_joined = set()
check_freq = dict(  ## seconds
    announcement=611,
    giveaway=299,
    game=59,
    self_mention=120
)

__AUTH__ = dict()
__TEST_SELF__ = False
__FIRST_TIME_RUN__ = False
__DEBUG__ = False
__TEST_SEND_ALL__ = False

my_dc_id = '<@364439430339231745>'


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if guild.name == GUILD:
            try:
                for ch in client.get_all_channels():
                    if ch.name in ('announcement', 'giveaway', 'game', 'test'):
                        client_channels[ch.name] = ch
                        # await ch.send(ch.name)
            except Exception as e:
                print(e)
                pass

            print(
                f'{bot.user} is connected to the following guild:\n'
                f'{guild.name}(id: {guild.id})'
            )

            channel_send_from_q.start()

            check_game.start()
            check_giveaway.start()
            check_announcement.start()
            # test_loop.start()
            #
            break


class http_request_thread():
    def __init__(self, max_connection_period=2, limit_period=1, wait=2, max_retry=5, max_thread=100):
        self.thread_count = 0
        self.req_ts = deque(maxlen=max_thread)
        self.max_connection_period = max_connection_period
        self.max_connection = max_thread
        self.limit_period = limit_period
        self.max_thread = max_thread
        self.wait = wait
        self.req_interval = 1.001 * limit_period / max_connection_period
        self.req_q = Queue()
        self.req_timer = RepeatedTimer(self.req_interval, self.req_loop)
        self.max_retry = max_retry
        self.req_timer.start()

    def queue_req(self, target_func, *args, **kwargs):
        callback = kwargs.pop('callback', None)
        if callback:
            item = ((target_func, callback), args, kwargs)
        else:
            item = (target_func, args, kwargs)

        self.req_q.put(item)

    def req_loop(self):
        if self.thread_count >= self.max_thread or self.req_q.empty():
            return
        target_callback_func, args, kwargs = self.req_q.get()
        th = Thread(target=self.do_req, args=(target_callback_func,) + args, kwargs=kwargs)
        self.thread_count += 1
        th.start()

    def do_req(self, target_callback_func, *args, **kwargs):
        def target_func_callback(*args, **kwargs):
            global db

            try:
                req_success = False
                ret = None
                for _ in range(self.max_retry):
                    ret = target_func(*args, **kwargs)
                    if type(ret) is dict:
                        if ('message' in ret and 'rate limit' in ret.get('message', '')):
                            req_success = False
                            sleep(ret.get('retry_after', self.wait) + 0.1 if type(ret) is dict else self.wait)
                            ret = None
                        elif 'message' in ret and 'Missing Access' in ret.get('message', ''):
                            # print('Missing access to', args[0])
                            db.delete(args[0])
                            ret = None
                        elif 'message' in ret and 'Unknown Channel' in ret.get('message', ''):
                            deleted_channel = db.delete(args[0])
                            if deleted_channel is not None and not deleted_channel.empty:
                                project = deleted_channel['project'].values
                                channel_name = deleted_channel['channel_name'].values
                                print('Unknown channel, deleting: {}/{}'.format(project[0],
                                                                                channel_name[0]))
                            ret = None
                        else:
                            print(ret)
                            ret = None
                    elif type(ret) is list:
                        req_success = True
                        break
                    else:
                        ret = None

                if req_success:
                    if callback and ret:
                        # loop = asyncio.new_event_loop()
                        # asyncio.set_event_loop(loop)
                        # loop = client.loop # event loop from dicordpy client

                        callback(ret)
                        # loop.run_until_complete(asyncio.wait([task]))

                else:
                    print('Request fail: ' + str(ret))
            except:
                traceback.print_exc()
            finally:
                self.thread_count -= 1

        if type(target_callback_func) is tuple or type(target_callback_func) is list:
            target_func, callback = target_callback_func
            target_func_callback(*args, **kwargs)
        else:
            target_func = target_callback_func
            callback = None
            target_func_callback(*args, **kwargs)
            # th = Thread(target=target_func_callback, args=args, kwargs=kwargs)
        # else:
        #     th = Thread(target=target_callback_func, args=args, kwargs=kwargs)
        # self.thread_count+=1
        # th.start()


@bot.command(description='test description')
async def test(ctx, *args):
    await ctx.send('test command with args: ' + (', '.join(args)))


@bot.command(description='test description')
@commands.has_permissions(administrator=True)
async def testa(ctx, *args):
    await ctx.send('test from admin')


@bot.command(description='add user auth')
@commands.has_permissions(administrator=True)
async def auth(ctx, auth):
    __AUTH__[ctx.author] = auth
    await ctx.send("{}'s auth: {}...{} stored.".format(ctx.author,
                                                       str(auth)[:3],
                                                       str(auth)[-3:-1]))


@bot.command(name='list-follow', description='list followed servers/channels')
@commands.has_permissions(administrator=True)
async def list_following(ctx, type=None):
    # db = discord_server_channel_db()
    if type is None:
        await ctx.send(db.data.to_markdown(tablefmt='grid'))
    else:
        pass

@bot.command(name='list-follow-project', description='list followed servers/channels')
# @commands.has_permissions(administrator=True)
async def list_following_project(ctx, type=None):
    # db = discord_server_channel_db()
    if type is None:
        await ctx.send(db.data['project'].unique().to_markdown(tablefmt='grid'))
    else:
        pass

@bot.command(name='reload', description='reload table')
@commands.has_permissions(administrator=True)
async def reload(ctx):
    global db
    db = discord_server_channel_db()
    await ctx.send('follow table reloaded!')


@bot.command(name='del', description='delete')
@commands.has_permissions(administrator=True)
async def delete(ctx, channel_link):
    deleted = db.delete(channel_link)
    if deleted is not None and not deleted.empty:
        await ctx.send('Delete: ' + channel_link)
    else:
        await ctx.send('Not found: ' + channel_link)


@bot.command(name='fo', description='follow: channel url, follow_type')
@commands.has_permissions(administrator=True)
async def follow(ctx,
                 channel_url,
                 follow_type: Literal['announcement', 'giveaway', 'game', 'an', 'gv', 'gm'] = None):
    channel = get_channel(channel_url, auth)

    if not follow_type:
        if re.search(r'announce|news|通告|公告|アナウン|お知|ticket', channel['name'], re.I): # also track ticket
            follow_type = 'announcement'
        elif re.search(r'giveaway|collab|抽獎', channel['name'], re.I):
            follow_type = 'giveaway'
        elif re.search(r'rumble|quiz|んぶる', channel['name'], re.I):
            follow_type = 'game'
        else:
            await ctx.send('Plz specify follow type for {}'.format(channel['name']))
            return

    guild = get_guild(channel['guild_id'], auth)

    if follow_type == 'an':
        follow_type = 'announcement'
    elif follow_type == 'gv':
        follow_type = 'giveaway'
    elif follow_type == 'gm':
        follow_type = 'game'
    last_msg_hash = ''  ## get_last_msg_hash(channel_url, auth)
    exists_str = ''

    # check if exists
    deleted = db.delete(channel_url)
    if deleted is not None and not deleted.empty:
        exists_str = 'Delete old record\n'

    db.insert(guild['name'], channel['name'], follow_type, '', channel_url, last_msg_hash, '')
    await ctx.send(exists_str + 'Follow: {}/{} as {}'.format(guild['name'], channel['name'], follow_type))


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.function = function
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        self.function(*self.args, **self.kwargs)
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


# @RateLimiter(max_calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
def get_api(url, authorization_token):
    header = get_header(authorization_token)
    try:
        res = requests.get(url, headers=header)
        res = res.json()
        return res
    except:
        print(res, "can't convert to json")
        traceback.print_exc()
        # pass


class discord_server_channel_db:
    def __init__(self, db_file='discord_server_channel.csv'):
        if db_file is None or not Path(db_file).exists():
            self.create_new(db_file)
        else:
            self.db = db_file
            self.data = pd.read_csv(self.db).fillna('')
        self.check_duplicate()

    def create_new(self, db_file=None):
        if db_file is None:
            db_file = 'discord_server_channel.csv'
        self.db = db_file
        self.data = pd.DataFrame([], columns=['project', 'channel_name', 'follow_type', 'has_mention', 'channel_url',
                                              'last_read', 'refresh_interval', 'at_time'], dtype=str)

    def update_last_read(self, i, new_last_read):
        with lock:
            self.data.loc[i, 'last_read'] = new_last_read
        self.save()

    def insert(self, *args):
        while len(args) < len(self.data.columns):
            args += ('',)
        new_row = pd.Series(args[:len(self.data.columns)], index=self.data.columns)
        with lock:
            self.data = self.data.append(new_row, ignore_index=True)
        self.save()

    def save(self):
        # self.check_duplicate()
        with lock:
            self.data.to_csv(self.db, index=False)

    def check_duplicate(self):
        with lock:
            self.data.drop_duplicates(inplace=True, ignore_index=True)

    def delete(self, channel_url):
        result = self.data[self.data['channel_url'] == channel_url]
        if not len(result):
            return
        with lock:
            self.data = (self.data[self.data['channel_url'] != channel_url]).reset_index(drop=True)
        return result


def get_header(token):
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
    }


def chat(message_txt, channel_id, authorization_token):
    header = get_header(authorization_token)
    channel_id = strip_channel_url(channel_id)

    msg = {
        "content": message_txt,
        "nonce": "82329451214{}33232234".format(random.randrange(0, 1000)),
        "tts": False,
    }
    url = "https://discord.com/api/v9/channels/{}/messages".format(channel_id)
    try:
        res = requests.post(url=url, headers=header, data=json.dumps(msg))
        if __DEBUG__:
            print(str(res.content))
    except:
        traceback.print_exc()
        # pass


def strip_channel_url(channel_url):
    found = re.search(r'\d+$', channel_url.strip())
    return found.group(0)


# def get_api(url, authorization_token):
#     header = get_header(authorization_token)
#     try:
#         res = requests.get(url, headers=header)
#         return res.json()
#     except:
#         traceback.print_exc()
#         # pass


def get_msg(channel_id, authorization_token, after=None, limit=100, around=None):
    channel_id = strip_channel_url(channel_id)

    url = "https://discord.com/api/v9/channels/{}/messages".format(channel_id)
    if after:
        url += '?after={}'.format(after)
    elif around:
        url += '?around={}'.format(around)
    if limit:
        url += ('&' if '?' in url else '?') + 'limit=' + str(limit)
    # if __DEBUG__:
    #     print('get_msg:', url)
    return get_api(url, authorization_token)

def get_message(channel_url, authorization_token):
    channel_id = strip_channel_url(channel_url)
    url = "https://discord.com/api/v9/channels/{}/message".format(channel_id)
    return get_api(url, authorization_token)

def get_channel(channel_id, authorization_token):
    channel_id = strip_channel_url(channel_id)
    url = "https://discord.com/api/v9/channels/{}".format(channel_id)
    return get_api(url, authorization_token)


def get_guild(guild_id, authorization_token):
    url = "https://discord.com/api/v9/guilds/{}".format(guild_id)
    return get_api(url, authorization_token)


def routine_checker():
    timers = dict()
    for check_type, interval_seconds in check_freq.items():
        timers[check_type] = RepeatedTimer(interval_seconds,
                                           checker, check_type)


@tasks.loop(seconds=60 * 60 * 24)
async def daily_checker():
    return
    # daily type, send at specific time, default 10AM
    result = db.data[db.data['follow_type'] == 'daily']
    for i, row in result.iterrows():
        at_time = row['at_time']
        if not at_time:
            at_time = ['0900']
        elif ',' in at_time:
            at_time = at_time.split(',')
        else:
            at_time = [at_time]

        # for trigger_time in at_time:
        # current_time =
        # target_time =
        # if target_time > current_time:
        #     th = Timer( , daily_routine)


@tasks.loop(seconds=check_freq['announcement'])
async def check_announcement():
    await checker('announcement')


@tasks.loop(seconds=check_freq['giveaway'])
async def check_giveaway():
    await checker('giveaway')


@tasks.loop(seconds=check_freq['game'])
async def check_game():
    await checker('game')


@tasks.loop(seconds=2)
async def test_loop():
    hq.queue_req(get_msg,
                 'https://discord.com/channels/1025595001549357067/1025971425791725710', auth,
                 callback=partial(test_callback, client_channels['test']))


def test_callback(channel, msg):
    channel_send_q.put((channel, msg))


@tasks.loop(seconds=5)
async def channel_send_from_q():
    batch = []
    while not channel_send_q.empty():
        batch.append(channel_send_q.get())
    if not batch:
        return
    to_be_sent = dict()
    for b in batch:
        check_type, msg = b
        if not check_type in to_be_sent:
            to_be_sent[check_type] = ''
        if len(msg) >= 300:
            msg = msg[:300]
        to_be_sent[check_type] += msg + '\n'
        if __DEBUG__:
            print('send msgs:', check_type, msg[:100])
    for check_type, msg in to_be_sent.items():
        channel = client_channels[check_type]
        msg = msg.rstrip()
        if len(msg) < 2000:
            await channel.send(msg)
        else:
            await channel.send(msg[:2000])


def get_last_msg_hash(channel_url, authorization_token):
    msg = get_msg(channel_url, authorization_token)
    if len(msg):
        last_msg = msg[-1]
        last_msg_hash = msg_hash(last_msg)
        return last_msg_hash
    return ''


async def checker(check_type):
    if __TEST_SELF__:
        return
    data = db.data
    if check_type != 'self_mention':
        pd_result = data[data['follow_type'] == check_type]

        for i, row in pd_result.iterrows():
            hq.queue_req(get_msg, row['channel_url'], auth,
                         extract_msgid(row['last_read']),
                         callback=partial(checker_callback, check_type, i, row))
            # break ## test break

    else:
        pass


def checker_callback(check_type, i, row, msgs):
    if __TEST_SEND_ALL__:
        try:
            channel_send_q.put((check_type, msgs[-1]['content'][:10]))
        except:
            pass

    elif msgs and len(msgs):
        ## first message is newest !!

        last_read_hash = row['last_read']
        newest_msg = None
        newest_msg_hash = ''
        try:
            newest_msg = msgs[0]
        except:
            print('msgs:', msgs)
            traceback.print_exc()
            return

        # last msg from me
        if newest_msg['author']['id'] in my_dc_id:
            return
        # last msg has my reaction emoji
        with suppress(Exception):
            for reaction in newest_msg['reactions']:
                if reaction['me']:
                    return

        if newest_msg:
            newest_msg_hash = msg_hash(newest_msg)

        if check_type == 'game' or check_type == 'giveaway':
            contains_last_read = False
            # if last_read_hash:
            #     for msg in msgs:
            #         if msg['id']==extract_msgid(last_read_hash):
            #             contains_last_read = True
            #             break

            has_valid_info = None
            for msg in msgs:
                # if contains_last_read:
                #     if msg['id']!=extract_msgid(last_read_hash):
                #         continue
                #     else:
                #         contains_last_read=False

                # with suppress(Exception):
                #     if not msg['embeds']:
                #         continue
                # with suppress(Exception):
                #     if 'Round' in msg['embeds'][0]['description']:
                #         continue

                if inform_giveaway(msg):
                    has_valid_info = msg
                    break

            if has_valid_info and last_read_hash != '' and not msg_has_my_emoji(newest_msg):
                new_msg = '{}/{} \n{}'.format(row['project'], row['channel_name'],
                                              row['channel_url'] + '/' + has_valid_info['id'])
                channel_send_q.put((check_type, new_msg))

            if newest_msg:
                if newest_msg_hash != last_read_hash:  ## new msgs!
                    db.update_last_read(i, newest_msg_hash)
                    # print(row['project'], last_msg_hash)

        else:
            if newest_msg:
                if newest_msg_hash != last_read_hash:  ## new msgs!

                    db.update_last_read(i, newest_msg_hash)

                    if __DEBUG__:
                        print('{}/{}:\n{}'.format(row['project'], row['channel_name'], newest_msg['content'][:100]))
                    if last_read_hash != '' and not msg_has_my_emoji(newest_msg):  ## last read not empty (first time)
                        new_msg = '{}/{} \n{}'.format(row['project'], row['channel_name'], row['channel_url'])
                        channel_send_q.put((check_type, new_msg))
                # elif __DEBUG__:
                #     print('{}/{}: {}'.format(row['project'], row['channel_name'], 'no new msgs'))


def msg_hash(msg):
    # return msg['id']
    if msg['edited_timestamp']:
        ts = msg['edited_timestamp']
    else:
        ts = msg['timestamp']
    return msg['id'] + '_' + ts


def extract_msgid(my_msg_hash):
    # return my_msg_hash
    msgid = re.search('^(\d+)_', my_msg_hash)
    if msgid:
        return msgid.group(1)


def add_reaction_to_rumble(msgs: list, authorization_token):
    '''
    https://discord.com/api/v9/channels/1030801986687344680/messages/1031398521720557578/reactions/Swrds:872886436012126279/@me?location=Message&burst=false
    '''

    sword_reaction = r'Swrds:872886436012126279/@me?location=Message&burst=false' # rumble royale
    sword_reaction2 = r'⚔️/@me?location=Message&burst=false' # battle royale


    for msg in msgs:
        bot_name=''
        with suppress(Exception):
            bot_name = msg['author']['username']
        if bot_name.lower()=='battle royale':
            url = "https://discord.com/api/v9/channels/{}/messages/{}/reactions/{}".format( \
                msg['channel_id'], msg['id'], sword_reaction2)
        else:
            url = "https://discord.com/api/v9/channels/{}/messages/{}/reactions/{}".format( \
                msg['channel_id'], msg['id'], sword_reaction)
        header = get_header(authorization_token)
        try:
            res = requests.put(url, headers=header)
            # res = res.json()
            # return res
        except:
            traceback.print_exc()
            # pass


def find_rumble_start_msg(msgs):
    ret = []
    for msg in msgs:
        try:
            if msg['author']['username'] == 'Rumble Royale' and \
                    msg['author']['bot'] == True and \
                    msg['reactions'][0]['emoji']['name'] == 'Swrds' and \
                    msg['reactions'][0]['me'] == False and \
                    'Starting in ' in msg['embeds'][0]['description'] and \
                    not 'Jump' in msg['embeds'][0]['description']:
                ret.append(msg)
        except:
            pass
    return ret

def rumble_jump_to_start(msg):
    with suppress(Exception):
        description=msg['embeds'][0]['description']
        url = re.search(r'https:\/\/discord.com\/channels\/\d+\/\d+\/(\d+)', description)
        if url:
            return dict(id=url.group(1))
    return dict(id='')


def has_rumble_sword_emoji(msg):
    with suppress(Exception):
        if (msg['reactions'][0]['emoji']['name'] == 'Swrds' or \
            msg['reactions'][0]['emoji']['name'] == '⚔') and \
                msg['reactions'][0]['me'] == False:
            return True
    return False


def msg_has_my_emoji(msg):
    with suppress(Exception):
        for reaction in msg['reactions']:
            if reaction['me']:
                return True
    return False


def inform_giveaway(msg, auto_click=True):
    info = is_giveaway(msg)
    if msg_has_my_emoji(msg):
        return False

    if info['has_mention']:
        return True
    if re.search('rumble royale|battle royale', info['bot'].lower()):
        if auto_click and has_rumble_sword_emoji(msg):
            add_reaction_to_rumble([msg], auth)
            rumble_msg_joined.add(msg['id'])
        if info['type'] == 'start':
            if msg['id'] in rumble_msg_joined:
                return False
            else:
                return True
        elif info['type'] == 'waiting':
            if rumble_jump_to_start(msg)['id'] in rumble_msg_joined:
                return False
            else:
                return True
        else:
            return False
    elif info['bot']:
        if info['type'] == 'giveaway':
            return True
        elif re.search('create|result|remind', info['type']):
            return False
        else:
            return True
    else:
        if msg_has_str(msg, 'http', 'premint', 'superful', 'alphabot', 'giveaway', '抽獎'):
            return True
        else:
            return False


def is_giveaway(msg):
    ret = dict(bot='', has_mention=has_mention(msg, my_dc_id), type='')
    with suppress(Exception):
        if not msg['author']['bot']:
            return ret
        else:
            ret['bot'] = msg['author']['username']

        if re.search('rumble royale|battle royale', msg['author']['username'].lower()):
            for embed in msg['embeds']:
                if 'hosted' in embed['description'].lower() \
                        or '主催者' in embed['description']:
                    ret['type'] = 'start'
                    break
                elif '🎉' in msg['content']:
                    ret['type'] = 'done,result'
                    break
                elif 'starting in' in embed['description'].lower() \
                        or '開始まで' in embed['description']:
                    ret['type'] = 'waiting'
                    break
                elif 'winner' in embed['title'].lower():
                    ret['type'] = 'done'
                    break
                elif 'cancelled' in embed['title'].lower():
                    ret['type'] = 'done,cancelled'
                    break
                elif 'round' in embed['title'].lower() \
                        or '回戦' in embed['title'] \
                        or '復活' in embed['title']:
                    ret['type'] = 'battle'
                    break
                else:
                    ret['type'] = 'other'

        elif msg['author']['username'] == 'Alphabot':
            if msg_has_str(msg, 'winner') or msg_has_str(msg, 'congratu'):
                ret['type'] = 'result'
            elif msg_has_str(msg, 'is minting'):
                ret['type'] = 'remind'
            else:
                ret['type'] = 'giveaway'
        elif msg['author']['username'] == 'Invite Tracker':
            if msg_has_str(msg, 'winner') or msg_has_str(msg, 'congratu'):
                ret['type'] = 'result'
            elif msg_has_str(msg, 'successfully created'):
                ret['type'] = 'create'
            elif msg_has_str(msg, 'giveaway'):
                ret['type'] = 'giveaway'
        elif msg['author']['username'] == 'GiveawayBot':
            if msg_has_str(msg, 'Winners: **'):
                ret['type'] = 'giveaway'
            elif msg_has_str(msg, 'Winners') or msg_has_str(msg, 'congratu'):
                ret['type'] = 'result'
        elif msg['author']['username'] == 'Giveaway Boat':
            if msg_has_str(msg, 'ended') or msg_has_str(msg, 'congratu'):
                ret['type'] = 'result'

    return ret


def msg_has_str(msg, *args):
    with suppress(Exception):
        for s in args:
            if s in msg['content'].lower():
                return True

    with suppress(Exception):
        for embed in msg['embeds']:
            for s in args:
                if s in embed['description'].lower():
                    return True
                if s in embed['title'].lower():
                    return True
    return False


def has_mention(msg, dcid=my_dc_id):
    with suppress(Exception):
        for embed in msg['embeds']:
            if dcid in embed['description']:
                return True
    with suppress(Exception):
        if dcid in msg['content']:
            return True
    with suppress(Exception):
        for mention in msg['mentions']:
            if mention['id'] in dcid:
                return True
    return False


def etheruko_interaction():
    header = get_header(auth)
    header['referer'] = 'https://discord.com/channels/997036565161312266/1014774016659169430'
    url = 'https://discord.com/api/v9/interactions'
    data = {"type": 3,
            "guild_id": "997036565161312266",
            "channel_id": "1014774016659169430",
            "message_flags": 0,
            "message_id": "1032511728912715786",
            "application_id": "1014732689405923408",
            "data": {"component_type": 2, "custom_id": "action"}}
    try:
        res = requests.post(url, headers=header, data=data)
        res = res.json()
        return res
    except:
        traceback.print_exc()


if __name__ == '__main__':
    auth = AUTH
    test_channel_url = 'https://discord.com/channels/1025595001549357067/1030801986687344680'
    # test_channel_url = 'https://discord.com/channels/942376101215359026/956474756557840384'
    # https://discord.com/channels/1012566778578219040/1019181253263622227/1032649553171730452
    # https://discord.com/channels/1012566778578219040/1019181253263622227/1032649634977431552
    # test_channel_url = 'https://discord.com/channels/1010432727939563630/1016704719890165781'
    # test_message_url = 'https://discord.com/channels/1025595001549357067/1030801986687344680/1030806384922611774'
    # msgs = get_msg(test_channel_url, auth,'1033355024346120242', limit=5)
    # url = 'https://discord.com/api/v9/channels/{}/messages/{}'.format(1019181253263622227, 1032649553171730452)
    # ret = get_api(url, auth)
    # etheruko_interaction()
    # add_reaction_to_rumble([msgs[-1]], auth)

    db = discord_server_channel_db()
    hq = http_request_thread()
    channel_send_q = Queue()

    # db.save()
    # msgs = get_msg(test_channel_id, auth)
    # channel = get_channel(test_channel_id, auth)
    # guild = get_guild('1025595001549357067', auth)
    # routine_checker()

    # routine_checker()
    # msgs = get_channel('https://discord.com/api/v9/channels/966184874677518386', auth)
    bot.run(TOKEN)
