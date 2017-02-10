import os
from time import sleep
from threading import Thread
from queue import Queue
from pprint import pprint
from random import choice
from functools import wraps, lru_cache

from telegram import Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from emoji import emojize
import vk_requests
from vk_requests import exceptions
import requests
import keen

import utils
from utils import parse_request
from longpoll import LongPoll

admin = int(os.environ.get('ADMIN_ID'))
log_channel = os.environ.get('LOG_CHAN')
token = os.environ.get('TOKEN')
app_name = os.environ.get('APPNAME')
app_id = os.environ.get('VK_APP_ID')
login = os.environ.get('VK_LOGIN')
phone_number = '+' + login
password = os.environ.get('VK_PASS')
scope = ['friends', 'photos', 'audio', 'video', 'pages', 'status', 'notes',
         'messages', 'wall', 'notifications', 'offline', 'groups', 'docs']


#  @lru_cache()
def get_user(user_id, name_case='nom'):
    try:
        user = api.users.get(user_ids=user_id, name_case=name_case)[0]
        return dict(user)
    except exceptions.VkException as exception:
        return str(exception)


def restricted(func):
    @wraps(func)
    def wrapped(bot, update, *args, **kwargs):
        try:
            user_id = update.message.from_user.id
        except (NameError, AttributeError):
            try:
                user_id = update.inline_query.from_user.id
            except (NameError, AttributeError):
                try:
                    user_id = update.chosen_inline_result.from_user.id
                except (NameError, AttributeError):
                    try:
                        user_id = update.callback_query.from_user.id
                    except (NameError, AttributeError):
                        print("No user_id available in update.")
                        return
        if user_id != admin:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(bot, update, *args, **kwargs)
    return wrapped


def queue_worker():
    while True:
        like_post(q.get())
        q.task_done()


def check_unread():
    dialogs = api.messages.getDialogs(count=200, unread=True)
    if dialogs['count'] > 0:
        msg_ids = []
        d = utils.plural(dialogs['count'])
        response = '<b>' + str(dialogs['count']) + ' ' + d + ' с непрочитанными сообщениями:</b>\n'
        for i in dialogs['items']:
            sleep(2)
            user_id = i['message']['user_id']
            msg_ids.append(i['message']['id'])
            try:
                user = api.users.get(user_ids=user_id)[0]
                full_name = utils.escapize(user['first_name'] + ' ' + user['last_name'])
                response += full_name + ' ' + str(user_id) + '\n'
            except exceptions.VkException:
                pass
            # User notification
            if user_id > 0:
                targets = utils.dbget(user_id)
                if targets is not None:
                    for t in targets:
                        u = api.users.get(user_ids=user_id, name_case='gen')[0]
                        u_nom = api.users.get(user_ids=user_id)[0]
                        full_name = utils.escapize(u['first_name'] + ' ' + u['last_name'])
                        full_name_nom = utils.escapize(u_nom['first_name'] + ' ' + u_nom['last_name'])
                        sud = str(u_nom['id'])
                        utils.dbadd('activity', '✉️ ' + full_name_nom + ' - ' + sud)
                        text = 'Есть новые сообщения от <b>' + full_name + '.</b> Id: ' + sud + '\nВведите <code>/d ' + sud + '</code> чтобы получить историю сообщений'
                        try:
                            tg.sendMessage(chat_id=t, text=text, parse_mode='HTML', disable_web_page_preview=True)
                        except Exception as e:
                            et = 'Exception:\n' + str(e) + '\nIn check_unread while sending to target - ' + str(t)
                            # noinspection PyTypeChecker
                            tg.send_message(admin, et)
                        sleep(2)
        tg.send_message(log_channel, response, 'HTML', True)
        try:
            api.messages.markAsRead(message_ids=msg_ids)
        except exceptions.VkException as e:
            ete = 'Exception:\n' + str(e) + '\nIn check_unread while markAsRead'
            # noinspection PyTypeChecker
            tg.send_message(admin, ete)


def get_wall(owner, count, offset=0):
    try:
        wall_request = api.wall.get(owner_id=owner, count=count, offset=offset)
        return wall_request
    except exceptions.VkException as e:
        print('Error while getting posts ' + str(e))
        return None


def another_like_function(items, success, error, who):
    already = 0
    available = utils.db_like(who)
    if available <= 0:
        return success, error, already, True
    for i in items:
        if i['likes']['can_like'] == 0:
            already += 1
            continue
        try:
            a = api.likes.add(type='post', owner_id=i['owner_id'], item_id=i['id'])
            if 'likes' in a:
                success += 1
                utils.limits(0 - 1)
                utils.db_like(who, 0 - 1)
        except exceptions.VkException as e:
            print('Error while another_like_function')
            print(str(success), str(error))
            print(str(e))
            error += 1
            sleep(4)
        sleep(3)
    return success, error, already, False


def like_post(args):
    print('Call function like_post')
    owner, chat_id, name, count, who, msg_id = args[0], args[1], args[2], args[3], args[4], args[5]
    already_liked = 0
    wall = get_wall(owner, count)
    if wall is None:
        tg.send_message(chat_id=chat_id, text='Не удалось получить ни одного поста', reply_to_message_id=msg_id)
        return
    total = wall['count']
    success, error, already, stop = another_like_function(wall['items'], 0, 0, who)
    already_liked += already
    if not stop:
        while already != 0:
            wall = get_wall(owner, count, already_liked)
            if wall is None:
                tg.send_message(chat_id=chat_id, text='Не удалось получить посты', reply_to_message_id=msg_id)
                break
            success, error, already, stop = another_like_function(wall['items'], success, error, who)
            if stop:
                break
            already_liked += already
            print('already: ' + str(already),
                  '\nalready_liked: ' + str(already_liked),
                  '\nsuccess: ' + str(success),
                  '\nerror: ' + str(error))
            sleep(1)
            if success >= count:
                break
    t = emojize('<b>{}</b> &lt; {}:revolving_hearts:\n:heart: {}/{}\n:broken_heart: {}'.format(utils.escapize(name), str(success),
                                                                                                str(success + already_liked),
                                                                                                str(total),
                                                                                                str(error)),
                use_aliases=True)
    keen.add_event("likes", {"success": success, "error": error})
    tg.send_message(log_channel, t, 'HTML', True)
    tg.send_message(chat_id, t, 'HTML', True)


# noinspection PyTypeChecker
def poll_callback(target, user_id, text, attachments):
    u = get_user(user_id)
    full_name = utils.escapize(u['first_name'] + ' ' + u['last_name'])
    utils.dbadd('activity', '✉️ ' + full_name + ' - ' + str(u['id']))
    if not attachments:
        try:
            tg.sendMessage(chat_id=target, text='<b>' + u['first_name'] + ' ' + u['last_name'] + ' &gt;&gt;&gt;</b>\n' +
                                                utils.escapize(text), parse_mode='HTML', disable_web_page_preview=True)
        except Exception as e:
            tg.send_message(admin,
                            'Exception:\n' + str(e) + '\nIn poll_callback while sending to target - ' + str(target))
    for a in attachments:
        if a['type'] == 'photo':
            try:
                with open(a['pic'], 'rb') as p:
                    tg.send_photo(chat_id=target, caption=u['first_name'] + ' ' + u['last_name'] + ' >>> ' + text,
                                  photo=p)
            except Exception as e:
                tg.send_message(admin,
                                'Exception:\n' + str(e) +
                                '\nIn poll_callback while sending to target - ' + str(target) +
                                '\nUser_id - ' + str(user_id))
        elif a['type'] == 'doc':
            pass


def parse_message(message_object, callback):
    user_id = message_object['user_id']
    text = message_object['body']
    targets = utils.dbget(user_id)
    if targets is None:
        targets = [log_channel]
    else:
        targets.append(log_channel)
    attachments = []
    if 'attachments' in message_object:
        for a in message_object['attachments']:
            if a['type'] == 'photo':
                keys = [k for k, v in a['photo'].items()]
                best_num = max(int(item.split('_')[1]) for item in keys if item.startswith('photo_'))
                url = a['photo']['photo_' + str(best_num)]
                photo = requests.get(url)
                file_name = str(a['photo']['id']) + ' ' + url.split('/')[-1]
                with open(file_name, 'wb') as pic:
                    pic.write(photo.content)
                attachments.append({'type': 'photo',
                                    'pic': file_name})
            elif a['type'] == 'sticker':
                pass
            elif a['type'] == 'wall':
                pass
            elif a['type'] == 'doc':
                pass
            elif a['type'] == 'audio':
                pass

    for t in targets:
        callback(t, user_id, text, attachments)

    for a in attachments:
        os.remove(a['pic'])


def online():
    while True:
        try:
            api.account.setOnline()
        except exceptions.VkException as exception:
            print(str(exception))
        sleep(600)


def longpoll_init():
    poll_data = api.messages.getLongPollServer()
    poll = LongPoll(poll_data['key'], poll_data['server'], poll_data['ts'])
    return poll


def longpoll_call():
    global poll
    response = poll.get()
    if response is None:
        poll = longpoll_init()
        sleep(1)
        return
    if not response:
        return
    # Main
    for box in response:
        if box[0] == 4:
            print(box)
            message_id = box[1]
            message_object = api.messages.getById(message_ids=message_id)
            if message_object['items'][0]['out'] == 1:
                continue
            keen.add_event("received", {"user_id": str(message_object['items'][0]['user_id'])})
            # mark as read
            try:
                t = api.messages.markAsRead(message_ids=message_id)
            except exceptions.VkException:
                print('mark as read error')
            # end
            pprint(message_object)
            parse_message(message_object['items'][0], poll_callback)


def longpoll_loop():
    while True:
        try:
            longpoll_call()
        except Exception as e:
            print(str(e))


def start(bot, update):
    update.message.reply_text(emojize('Введи /h для получения списка команд :wink:', use_aliases=True))


def hello(bot, update):
    update.message.reply_text(emojize(utils.help_text + utils.escapize(utils.cmd_list), use_aliases=True), parse_mode='HTML')


@parse_request
def send(bot, update, cmd=None):
    blacklist = utils.dbget('send')
    if blacklist is not None:
        if str(update.message.from_user.id) in blacklist:
            update.message.reply_text(emojize(choice(utils.blacklist_strings), use_aliases=True))
            return
    if not cmd:
        return
    data = ''
    user = get_user(cmd[0])
    try:
        data = api.messages.send(peer_id=user['id'], message=cmd[1])
    except exceptions.VkException as exception:
        data = str(exception)
    except TypeError:
        data = emojize('Что-то пошло не так :confused:', use_aliases=True)  # if not enough args
    finally:
        if isinstance(data, int):
            full_name = utils.escapize(user['first_name'] + ' ' + user['last_name'])
            t = '<b>' + full_name + ' &lt;&lt;&lt;</b>\n' + utils.escapize(cmd[1])
            update.message.reply_text(t, parse_mode='HTML', disable_web_page_preview=True)
            tg.send_message(log_channel, t, 'HTML', True)
            utils.dbadd('activity', '✉️ ' + full_name + ' - ' + str(user['id']))
            keen.add_event("sended", {"by_user": update.message.from_user.id, "to_user": user['id']})
        else:
            update.message.reply_text(str(data))


# noinspection PyTypeChecker,PyUnreachableCode
@restricted
@parse_request
def secrets(bot, update, cmd=None):
    update.message.reply_text('Nope.')
    return
    if not cmd:
        tg.send_message(admin, utils.secrets_help)
        return
    if cmd[0].startswith('rese'):
        utils.reset()
        print('Reset by admin')
    elif cmd[0].startswith('lyk'):
        try:
            utils.db_like(str(update.message.reply_to_message.from_user.id), int(cmd[0].split('.')[1]))
        except Exception as e:
            tg.send_message(admin, utils.secrets_help + '\n' + str(e))
    elif cmd[0].startswith('drop'):
        k = cmd[0].split('.')[1]
        utils.dbdropkey(k)
        update.message.reply_text(k + ' droped')
    elif cmd[0].startswith('db'):
        try:
            query = cmd[0].split('.')
            if query[1] == 'add':
                utils.dbadd(query[2], str(update.message.reply_to_message.from_user.id))
                tg.send_message(admin, str(utils.dbget(query[2])))
            elif query[1] == 'del':
                utils.dbdel(query[2], str(update.message.reply_to_message.from_user.id))
                tg.send_message(admin, str(utils.dbget(query[2])))
        except Exception as e:
            tg.send_message(admin, utils.secrets_help + '\n' + str(e))


@parse_request
def info(bot, update, cmd=None):
    if cmd:
        try:
            user_object = \
                api.users.get(user_ids=cmd[0], fields='online,photo_max,status,sex,can_write_private_message')[0]
        except exceptions.VkException:
            update.message.reply_text(emojize('Ошибка :disappointed:', use_aliases=True))
            return
        photo = requests.get(user_object['photo_max'])
        sex = line = ''
        can_write = 'Не могу отправлять сообщения'
        if 'sex' in user_object:
            if user_object['sex'] == 1:
                sex = '(Женский пол)'
            elif user_object['sex'] == 2:
                sex = '(Мужской пол)'
            elif user_object['sex'] == 0:
                sex = '(Животное)'
        else:
            sex = '(Животное)'
        if user_object['online'] == 1:
            line = 'В сети'
        elif user_object['online'] == 0:
            line = 'Не в сети'
        if user_object['can_write_private_message'] == 1:
            can_write = 'Могу отправлять сообщения'
        status = user_object['status'] if 'status' in user_object else ''
        caption = user_object['first_name'] + ' ' + user_object[
            'last_name'] + sex + ' - ' + status + '\n' + line + ', ' + can_write
        file_name = str(cmd[0]) + ' ' + user_object['photo_max'].split('/')[-1]
        with open(file_name, 'wb') as p:
            p.write(photo.content)
        with open(file_name, 'rb') as p:
            tg.send_photo(chat_id=update.message.chat.id, caption=caption, photo=p)
        keen.add_event("info", {"by_user": update.message.from_user.id, "req_user": cmd[0]})
        os.remove(file_name)


@parse_request
def sethook(bot, update, cmd=None):
    if not cmd:
        return
    blacklist = utils.dbget('hook')
    if blacklist is not None:
        if str(update.message.from_user.id) in blacklist:
            update.message.reply_text(emojize(choice(utils.blacklist_strings), use_aliases=True))
            return
    try:
        hook_vk_user = api.users.get(user_ids=cmd[0])[0]['id']
    except exceptions.VkException:
        update.message.reply_text(emojize('Ошибка :disappointed:', use_aliases=True))
        return
    utils.dbadd(hook_vk_user, update.message.chat.id)
    print(str(utils.dbget(hook_vk_user)))
    update.message.reply_text(emojize('Хорошо :ok_hand:', use_aliases=True))
    keen.add_event("set_hook", {"by_user": update.message.from_user.id, "req_user": cmd[0]})


@parse_request
def delhook(bot, update, cmd=None):
    if not cmd:
        return
    blacklist = utils.dbget('hook')
    if blacklist is not None:
        if str(update.message.from_user.id) in blacklist:
            update.message.reply_text(emojize(choice(utils.blacklist_strings), use_aliases=True))
            return

    try:
        hook_vk_user = api.users.get(user_ids=cmd[0])[0]['id']
    except exceptions.VkException:
        update.message.reply_text(emojize('Ошибка :disappointed:', use_aliases=True))
        return
    utils.dbdel(hook_vk_user, update.message.chat.id)
    print(str(utils.dbget(hook_vk_user)))
    update.message.reply_text(emojize('Ок :dash:', use_aliases=True))
    keen.add_event("del_hook", {"by_user": update.message.from_user.id, "req_user": cmd[0]})


def history_text(user_id, page: int) -> str:
    user = get_user(user_id, 'ins')
    if isinstance(user, str):
        raise Exception(user)
    message_list = []
    try:
        history_response = api.messages.getHistory(user_id=user['id'], offset=page*20)['items']
    except exceptions.VkException as e:
        raise e
    for i in history_response:
        if i['out'] == 0:
            message_list.append({'&gt;&gt;&gt; ': i['body']})
        else:
            message_list.append({'&lt;&lt;&lt; ': i['body']})
    text_form = 'Сообщения с <b>' + user['first_name'] + '</b>\n'
    for item in message_list:
        for k, v in item.items():
            text_form = text_form + '\n' + k + utils.escapize(v)
    user_nom = get_user(user)
    if isinstance(user_nom, str):
        raise Exception(user_nom)
    nom_name = user_nom['first_name'] + ' ' + user_nom['last_name']
    utils.dbadd('activity', '📃️ ' + nom_name + ' - ' + str(user_nom['id']))
    keen.add_event("history", {"to_user": user_nom['id']})
    return text_form


@parse_request
def history(bot, update, cmd=None):
    if not cmd:
        return
    try:
        msg = history_text(cmd[0], 0)
        update.message.reply_text(msg, parse_mode = 'HTML')
    except Exception as e:
        update.message.reply_text(e)
        return


def activity(bot, update):
    data = utils.dbget('activity')
    t = ''
    for l in data:
        t += l + '\n'
    update.message.reply_text(t)


def counts(bot, update):
    x = utils.db_like(update.message.from_user.id)
    update.message.reply_text(emojize('Вы можете поставить ещё ' + str(x) + ' сердечек!', use_aliases=True))


def total_count(bot, update):
    x = utils.limits()
    update.message.reply_text(str(x))


@parse_request
def friend(bot, update, cmd=None):
    if cmd:
        try:
            user = api.users.get(user_ids=cmd[0])[0]
        except exceptions.VkException as exception:
            update.message.reply_text(str(exception))
            return
        try:
            api.friends.add(user_id=user['id'])
        except exceptions.VkException as e:
            update.message.reply_text(str(e))
            return
        update.message.reply_text(emojize('Хорошо :relaxed:', use_aliases=True))
        name = user['first_name'] + ' ' + user['last_name']
        utils.dbadd('activity', '➕️️ ' + name + ' - ' + str(user['id']))
        keen.add_event("friend", {"by_user": update.message.from_user.id, "req_user": cmd[0]})


@parse_request
def like(bot, update, cmd=None):
    print('Call like(): ' + str(update.message.text))
    blacklist = utils.dbget('like')
    if blacklist is not None:
        if str(update.message.from_user.id) in blacklist:
            update.message.reply_text(emojize(choice(utils.blacklist_strings), use_aliases=True))
            return
    if not cmd:
        return
    try:
        user = api.users.get(user_ids=cmd[0])[0]
        owner = user['id']
        name = user['first_name'] + ' ' + user['last_name']
    except exceptions.VkException:
        group = api.groups.getById(group_id=cmd[0])[0]
        owner = 0 - group['id']
        name = group['name']
    print('calling db')
    available = utils.db_like(update.message.from_user.id)
    print(str(available) + ' likes for ' + str(update.message.from_user.id))
    count = 10 if available >= 10 else available
    if count <= 0:
        update.message.reply_text(emojize('У вас не осталось сердечек :disappointed:', use_aliases=True))
        keen.add_event("not_enough_user_likes", {"by_user": update.message.from_user.id})
        return
    elif utils.limits() <= count:
        update.message.reply_text(emojize('Исчерапан дневной лимит бота :disappointed:', use_aliases=True))
        keen.add_event("not_enough_global_likes", {"by_user": update.message.from_user.id})
        return
    else:
        q.put([owner, update.message.chat.id, name, count, update.message.from_user.id, update.message.message_id])
        update.message.reply_text(emojize('Ок, выполняю :sparkling_heart:', use_aliases=True))
        utils.dbadd('activity', '❤️️ ' + name + ' - ' + str(owner))


def send_photo(bot, update):
    return


def anything(bot, update):
    return


tg = Bot(token)
api = vk_requests.create_api(app_id=app_id, login=login,
                             password=password, phone_number=phone_number,
                             api_version='5.62', scope=scope)

q = Queue()
t = Thread(target=queue_worker)
t.setDaemon(True)
t.start()

sleep(1)
Thread(target=check_unread, args=[]).start()
Thread(target=online, args=[]).start()

poll = longpoll_init()
Thread(target=longpoll_loop, args=[]).start()

updater = Updater(token)
updater.start_webhook(listen="0.0.0.0", port=int(os.environ.get('PORT', '5000')), url_path=token)
updater.bot.setWebhook("https://{}.herokuapp.com/{}".format(app_name, token))

updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(CommandHandler('h', hello))
updater.dispatcher.add_handler(CommandHandler('s', send))
updater.dispatcher.add_handler(CommandHandler('i', info))
updater.dispatcher.add_handler(CommandHandler('d', history))
updater.dispatcher.add_handler(CommandHandler('l', like))
updater.dispatcher.add_handler(CommandHandler('a', friend))
updater.dispatcher.add_handler(CommandHandler('x', counts))
updater.dispatcher.add_handler(CommandHandler('tx', total_count))
updater.dispatcher.add_handler(CommandHandler('sethook', sethook))
updater.dispatcher.add_handler(CommandHandler('delhook', delhook))
updater.dispatcher.add_handler(CommandHandler('activity', activity))
updater.dispatcher.add_handler(CommandHandler('we', secrets))
updater.dispatcher.add_handler(MessageHandler(Filters.photo, send_photo))
updater.dispatcher.add_handler(MessageHandler(Filters.all, anything))
updater.idle()
