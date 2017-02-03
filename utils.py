import os
import redis
import json

r = redis.from_url(os.environ.get("REDIS_URL"), charset="utf-8", decode_responses=True)

# heroku logs --tail | grep -v router --line-buffered
# db format -
# 'string key': ['list', 'with', 'strings']

# reserved redis keys:
# 'send', 'like', 'hook'
# 'activity'
# 'l{some number} like l5239812343'
# 'll'
# 'limit'
#
# and any numbers

blacklist_strings = ['Ты :shit:', 'Повтори, я не расслышал :information_desk_person:',
                     'Ооо... Ты в чёрном списке :smiling_imp:']
secrets_help = '/we db.add/del.send/like/hook\n/we drop.send\n/we lyks.10'

help_text = '<b>Список команд:</b>'
cmd_list = '''
/h - список команд
/s <id> <text> - отправить сообщение
/i <id> - получить информацию о пользователе
/d <id> - история сообщений
/l <id> - залайкать стену
/x - сколько лайков вы можете поставить
/a <id> - добавить в друзья
/sethook <id> - пересылать сообщения в этот чат
/delhook <id> - перестать пересылать сообщения
/activity - список последних действий
'''

bot_name = os.environ.get('BOT_USERNAME')
cmd_arg_1 = []
for command in ['/sethook', '/delhook', '/i', '/we', '/d', '/l', '/a']:
    cmd_arg_1.append(command)
    cmd_arg_1.append(command + bot_name)

num = {
    '0': 'диалогов',
    '1': 'диалог',
    '2': 'диалога',
    '3': 'диалога',
    '4': 'диалога',
    '5': 'диалогов',
    '6': 'диалогов',
    '7': 'диалогов',
    '8': 'диалогов',
    '9': 'диалогов',
}


def plural(number):
    if 5 <= int(str(number)[-2:]) <= 20:
        return 'дилогов'
    else:
        return num[str(number)[-1:]]


def escapize(text):
    return text.replace('&', '&amp;') \
        .replace('<', '&lt;') \
        .replace('>', '&gt;')


def drop():
    pass  # r.flushall()


def dbadd(key, value):
    data = dbget(str(key))  # list
    if data is not None:
        if str(value) in data:
            if key == 'activity':
                data.remove(str(value))
                data = [str(value)] + data
                r.set(key, json.dumps(data))
                return
            else:
                return
        else:
            if key == 'activity':
                data = [str(value)] + data
                if len(data) > 12:
                    data.pop()
                r.set(key, json.dumps(data))
                return
            else:
                data.append(str(value))
                r.set(key, json.dumps(data))
                return
    else:
        r.set(key, json.dumps([str(value)]))
        return


def dbget(key) -> list or None:
    """
    Returns list of chat_ids
    """
    data = r.get(str(key))
    if data is None:
        return None
    return json.loads(data)


def dbdel(key, element):
    data = dbget(str(key))
    if data is None:
        return None
    data.remove(str(element))
    if not data:
        r.delete(str(key))
    else:
        r.set(key, json.dumps(data))


def db_like(user_id, count: int = 0) -> int:
    """
    Returns current count
    """
    u = 'l' + str(user_id)
    if count != 0:
        data = r.get(u)
        if data is not None:
            r.set(u, str(int(data) + count))
        else:
            r.set(u, str(50 + count))
            dbadd('ll', str(user_id))
    ret = r.get(u)
    if ret is not None:
        return int(ret)
    else:
        r.set(u, str(50 + count))
        dbadd('ll', str(user_id))
        return 50


def limits(count: int = 0):
    if count != 0:
        data = r.get('limit')
        if data is not None:
            r.set('limit', str(int(data) + count))
        else:
            r.set('limit', '500')
            return 500 + count
    ret = r.get('limit')
    if ret is not None:
        return int(ret)
    else:
        r.set('limit', '500')
        return 500


def dbdropkey(key):
    r.delete(str(key))


def parse_request(f):
    def wrapper(*args, **kw):
        data = ''
        txt = args[1].message.text
        cmd = txt.split()
        if cmd[0] in ['/s', '/s@vkrebornbot']:
            data = parser(txt, 2)
        elif cmd[0] in cmd_arg_1:
            data = parser(txt, 1)
        args += data,
        return f(*args, **kw)

    return wrapper


def parser(text, spaces):
    args = []
    try:
        text = text.split(' ', spaces)
        for x in range(spaces + 1):
            args.append(text[x])
    except IndexError:
        args = None
    if args is not None:
        return args[1:]
    else:
        return False
