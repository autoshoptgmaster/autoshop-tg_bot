import requests, logging
from telebot import TeleBot
from telebot import types

import messages
import db_api
import time
import functions
import random
import ast
from logger import logger

import qiwi
import settings
import flask
import threading
from yandex_money import api


users_menu = {}
bans = {}
tb = TeleBot(settings.telegram_token, threaded=True)
bot_info = tb.get_me()
repost_message = None
answ = functions.AnswFunctions(tb=tb, db=db_api)
helpers = functions.helpers()
wallet = api.Wallet(access_token=settings.ya_token)

to_replace = {'%all_users%': lambda: db_api.count.users(),
              '%users_today%': lambda: db_api.count.activity(date=time.strftime("%d/%m/%Y")),
              '%posts_count%': lambda: db_api.count.channels(active=1),
              '%views_count%': lambda: db_api.count.posts(status='Active'),
              '%money_for_views%': lambda: list(db_api.sumof.transactions(row='count', type='view_pay'))[0]['sum(count)'],
              '%money_for_post%': lambda: list(db_api.sumof.transactions(row='count', type='post_pay'))[0]['sum(count)'],
              '%money_out%': lambda: list(db_api.sumof.transactions(row='count', type='pay_out'))[0]['sum(count)']}


def get_user(id, message):
    user = db_api.get.users(user_id=id)
    if user:
        return user[0]
    else:
        db_api.insert.users(user_id=message.from_user.id, username=message.from_user.username, chat_id=message.chat.id)

    tb.send_message(chat_id=message.chat.id, text='Чтобы начать - напиши /start')
    return None


def send_message(message, mobj, **kwargs):
    try:
        if 'text' in mobj:
            text = mobj['text']
        else:
            text = ' '

        if 'markup' in mobj:
            markup = answ.gen(mobj['markup'])
        else:
            return tb.send_message(message.chat.id, text=text, **kwargs)
        if message.from_user.id in settings.admins:
            markup = answ.gen(mobj['markup'])
            try:
                markup.row(types.KeyboardButton('Админка'))
            except:
                pass
        return tb.send_message(message.chat.id, text=text, reply_markup=markup, **kwargs)
    except:
        return


@tb.message_handler(commands=['start', 'help'])
def send_welcome(message):
    send_message(message, messages.start)
    user = db_api.get.users(user_id=message.from_user.id)

    if len(user) > 0:
        return

    db_api.insert.users(user_id=message.from_user.id, username=message.from_user.username, chat_id=message.chat.id)
    users_menu.update({message.from_user.id: 'home'})
    db_api.insert.activity(
        trans_id=random.randint(0, 99999), type='new_user',
        user_id=message.from_user.id, date=time.strftime("%d/%m/%Y")
    )

    if len(message.text.split(' ')) > 1 and message.text.split(' ')[1] != str(message.from_user.id):
        helpers.new_referal(db_api, message.from_user.id, message.text.split(' ')[1])
        answ.balance(
            type='pay_new_ref',
            user={},
            count=settings.new_ref_cost,
            user_id=message.text.split(' ')[1]
        )

    return


@tb.message_handler(
    content_types=["text", 'channel', 'forward_from', 'post', 'sticker', 'forward_from_chat', 'audio', 'photo', 'video_note', 'voice', 'location', 'caption', 'game', 'sticker',
                   'document', 'venue', 'video', 'contact', 'entities', 'photo'], func=lambda m: m.forward_from_chat is not None)
def nuks(message):
    if message.forward_from_chat.type == 'channel':
        user = get_user(message.from_user.id, message)

        if user:
            if message.from_user.id not in users_menu.keys():
                menu = user['menu']
            else:
                menu = users_menu[message.from_user.id]
        else:
            return

        try:
            add_info = ast.literal_eval(db_api.get.users(user_id=message.from_user.id)[0]['add_info'])
        except:
            return

        if menu == 'advert':
            # prin(message)
            try:
                channels = db_api.get.channels(channel_name='@' + message.forward_from_chat.username)
            except:
                tb.send_message(
                    message.chat.id,
                    text=messages.for_advert_admin['error_not_admin']['text'],
                    reply_markup=answ.gen_inl(messages.for_advert_admin['error_not_admin']['markup'])
                )
                return
            if len(channels) > 0:
                if not channels[0]['active'] and message.from_user.id == channels[0]['user_id']:
                    pass
                else:
                    return send_message(message, messages.for_advert_admin['already_in'])

            add_info.update({'channel_name': '@' + message.forward_from_chat.username, 'channel_id': message.forward_from_chat.id})
            db_api.insert.users(user_id=message.from_user.id, add_info=str(add_info))
            admin = answ.chechk_admin('@' + message.forward_from_chat.username, bot_info.username)
            if admin:
                send_message(message, messages.for_advert_admin['success'])

                db_api.insert.users(user_id=message.from_user.id, menu='advert_enter_cost')
                return
            else:
                tb.send_message(
                    message.chat.id,
                    text=messages.for_advert_admin['error_not_admin']['text'],
                    reply_markup=answ.gen_inl(messages.for_advert_admin['error_not_admin']['markup']))
                return
        elif menu == 'advert-view':
            db_api.insert.posts(
                from_chat_id=message.chat.id,
                from_chat_username=message.forward_from_chat.username,
                forward_from_message_id=message.message_id,
                user_id=user.get('user_id'),
                status='Edit'
            )
            db_api.insert.users(user_id=message.from_user.id, menu='advert-view-cost')

            tb.send_message(chat_id=message.chat.id, text=messages.post_received['text'])
        else:
            return
    pass


@tb.message_handler(
    content_types=["text", 'channel', 'post', 'sticker', 'audio', 'photo', 'video_note', 'voice', 'location', 'caption', 'document', 'forward_from', 'forward_from_chat'])
def nuka(message):
    # if message.forward_from_chat:
    #     prin(message)

    user_id = message.from_user.id
    global repost_message
    text = message.text
    user = get_user(message.from_user.id, message)

    if not user:
        return
    try:
        add_info = ast.literal_eval(db_api.get.users(user_id=message.from_user.id)[0]['add_info'])
    except:
        add_info = {}

    if message.from_user.id not in users_menu:
        menu = user['menu']
    else:
        menu = users_menu[message.from_user.id]

    if text in ['⛔️ Отмена', '🔙 Начало']:
        db_api.insert.users(user_id=user['user_id'], menu='home')
        users_menu.update({message.from_user.id: 'home'})
        send_message(message, messages.start)
        return
    if text == '👁‍🗨 Смотреть':
        ###########################################################################
        t = threading.Thread(target=answ.post_view, kwargs={'user': user, 'send_message': send_message, 'message': message})
        t.start()
        return
    # Смотрим посты
    elif text == '📲 Подписаться':
        t = threading.Thread(target=answ.sub, kwargs={'user': user, 'send_message': send_message, 'message': message})
        t.start()
        return
    elif text == '🚀 Продвижение':
        mes_id = send_message(message, messages.for_advert, parse_mode='Markdown')
        users_menu.update({user_id: 'advert_ind'})
        add_info.update({'last_adv': mes_id.message_id})
        db_api.insert.users(user_id=user_id, menu='advert', add_info=str(add_info))
        return
    elif text == '👁‍🗨 Просмотры':
        m = """📢Для того, чтобы купить просмотры поста из вашего канала, просто сделайте репост нужного поста из Вашего канала в этот бот."""
        mes_id = send_message(message, {'text': m}, parse_mode='Markdown')
        users_menu.update({user_id: 'advert-view'})
        add_info.update({'last_adv': mes_id.message_id})
        db_api.insert.users(user_id=user_id, menu='advert-view', add_info=str(add_info))
        return
    elif text == '📲 Подписчики':
        # try:
        #     if 'last_adv' in add_info:
        #         tb.delete_message(chat_id=message.chat.id, message_id=add_info['last_adv'])
        # except:
        #     pass
        mes_id = send_message(message, messages.for_subs, parse_mode='Markdown')
        users_menu.update({user_id: 'advert'})
        add_info.update({'last_adv': mes_id.message_id})
        db_api.insert.users(user_id=user_id, menu='advert', add_info=str(add_info))

        return

    elif text == '👥 Рефералы':
        referals = []

        referal = db_api.get.users(user_id=user['referal'])
        refs2nd = 0

        refs = ast.literal_eval(user['refs'])

        if len(refs) > 0:
            for fstref in refs:
                try:
                    secref = ast.literal_eval(db_api.get.users(user_id=fstref)[0]['refs'])
                except:
                    secref = []
                refs2nd = refs2nd + len(secref)
        if len(refs) < 1:
            referals = 'нет'
        else:
            referals = len(refs)
        if refs2nd < 1:
            refs2nd = 'нет'
        else:
            refs2nd = refs2nd

        if len(referal) < 1:

            ref_answ = {
                'text': '''👤Вас пригласил: пришел сам
👥Ваши рефералы 1го уровня: {}
👥Ваши рефералы 2го уровня: {}
Реферальная ссылка:
https://t.me/{}?start={}

💸Доход с рефералов 1 Уровня - {}%
💸Доход с рефералов 2 Уровня - {}%

Если пользователь перейдет по вашей ссылке вы получите {} руб'''.format(
                    referals, refs2nd, bot_info.username, user['user_id'],
                    settings.ref_view_pay_1lvl*100, settings.ref_view_pay_2lvl*100,
                    settings.new_ref_cost),
                'markup': messages.start['markup']
            }

        else:
            if referal[0]['username'] is not None:
                ref_answ = {
                    'text': '''👤Вас пригласил: [Реферал](tg://user?id={})
👥Ваши рефералы 1го уровня: {}
👥Ваши рефералы 2го уровня: {}
Реферальная ссылка:
[https://t.me/{}?start={}](https://t.me/{}?start={})

💸Доход с рефералов 1 Уровня - {}%
💸Доход с рефералов 2 Уровня - {}%

Если пользователь перейдет по вашей ссылке вы получите {} руб'''.format(
                        user['referal'], referals, refs2nd, bot_info.username, user['user_id'], bot_info.username, user['user_id'],
                        settings.ref_view_pay_1lvl*100, settings.ref_view_pay_2lvl*100,
                        settings.new_ref_cost),
                    'markup': messages.start['markup']
                }
                try:
                    return send_message(message, ref_answ, disable_web_page_preview=True)
                except:
                    ref_answ = {
                        'text': '''👤Вас пригласил: {}
👥Ваши рефералы 1го уровня: {}
👥Ваши рефералы 2го уровня: {}
Реферальная ссылка:
https://t.me/{}?start={}

💸Доход с рефералов 1 Уровня - {}%
💸Доход с рефералов 2 Уровня - {}%

Если пользователь перейдет по вашей ссылке вы получите {} руб'''.format(
                            referal[0]['user_id'], referals, refs2nd, bot_info.username, user['user_id'], bot_info.username, user['user_id'],
                            settings.ref_view_pay_1lvl*100, settings.ref_view_pay_2lvl*100,
                            settings.new_ref_cost),
                        'markup': messages.start['markup']
                    }
                    return send_message(message, ref_answ, disable_web_page_preview=True)
            else:
                ref_answ = {
                    'text': '''👤Вас пригласил: @{}
👥Ваши рефералы 1го уровня: {}
👥Ваши рефералы 2го уровня: {}
Реферальная ссылка:
https://t.me/{}?start={}

💸Доход с рефералов 1 Уровня - {}%
💸Доход с рефералов 2 Уровня - {}%

Если пользователь перейдет по вашей ссылке вы получите {} руб'''.format(
                        referal[0]['username'], referals, refs2nd, bot_info.username, user['user_id'], bot_info.username, user['user_id'],
                        settings.ref_view_pay_1lvl*100, settings.ref_view_pay_2lvl*100,
                        settings.new_ref_cost),
                    'markup': messages.start['markup']
                }
        return send_message(message, ref_answ, disable_web_page_preview=True)

    # Статистика todo в статистике ебнуть всю статистику проекта А именно: пользователей всего,пользователей за сегодня, постов всего,Заработаннт всего Выплачено всего

    elif text == '♻️ Статистика':
        obj = {}
        obj.update(messages.stat)

        for i in to_replace:
            obj['text'] = obj['text'].replace(i, str(round((lambda x: x if x is not None else 0)(to_replace[i]()), 2)))

        return send_message(message, obj, parse_mode='Markdown')

    elif text == '⚠️ Информация':
        return send_message(message, messages.rules, parse_mode='Markdown')

    elif text == '💶 Мой доход':
        try:
            view_bal = round(list(db_api.sumof.transactions(row='count', type='view_pay', user_id=message.from_user.id))[0]['sum(count)'], 2)
        except:
            view_bal = 0
        try:
            post_bal = round(list(db_api.sumof.transactions(row='count', type='post_pay', user_id=message.from_user.id))[0]['sum(count)'], 2)
        except:
            post_bal = 0
        try:
            ref_pay = round(user['ref_pay'], 2)
        except:
            ref_pay = 0
        try:
            usr_chn = ast.literal_eval(user['channels'])
        except:
            usr_chn = []
        try:
            view_count = db_api.count.post_view(user_id=user_id)
        except:
            view_count = 0
        msg = {
            'text': '''💶 Мой доход:
    🔑  Мой ID: {}
    ➕ Сделано подписок: {}
    👁  Просмотрено репостов: {}
    ✔️  Заработано с подписок:  {}p
    ✔️  Заработано с просмотра репостов: {}p
    🔗 Доход с привлечения: {}p
    💰 Всего заработано: {}p
    💸 Выведено всего: {}p
    '''.format(message.from_user.id, len(usr_chn), view_count, view_bal, post_bal, round(ref_pay, 2), round(view_bal + post_bal + round(ref_pay, 2), 2),
               round((lambda x: x if x is not None else 0)(list(db_api.sumof.transactions(row='count', type='pay_out', user_id=message.from_user.id))[0]['sum(count)']), 2)
               ),
            'markup': [['👥 Рефералы'], ['◀️ Вернуться']]
        }
        send_message(message, msg)
        return

    elif text == '🏦 Баланс':
        answr = {'text': '''💰 Ваш общий баланс: {}р
        🏦 Баланс: {}р
        👥 Реферальный баланс: {}р'''.format(round(user['balance'] + user['ref_balance'], 2), round(user['balance'], 2), round(user['ref_balance'], 2)),
                 'markup': [['📤 Вывести', '📥 Пополнить'], ['◀️ Вернуться']]}
        send_message(message, answr)
        return

    elif text == '📤 Вывести':
        answr = {'text': '''Выберете способ вывода:''',
                 'markup': [['Яндекс', 'QIWI'], ['◀️ Вернуться']]}
        send_message(message, answr)
        return

    elif text == 'QIWI':
        # ############### QIWI ###########
        obj = {}
        obj.update(messages.out_pay)
        obj['text'] = obj['text'].replace('%max_money%', str(round(user['balance'] + user['ref_balance'])))
        send_message(message, obj)
        db_api.insert.users(user_id=user['user_id'], menu='out_pay_qiwi')
        users_menu.update({message.from_user.id: 'out_pay_qiwi'})
        return

    if user.get('menu', '') in ['out_pay_qiwi']:
        count = helpers.ifloat(text)
        if count:
            if count < settings.min_out_pay:
                return send_message(message, messages.out_pay['error_min_pay'])
            if count > user['balance'] + user['ref_balance']:
                return send_message(message, messages.out_pay['error_max_pay'])

            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'count_to_out_pay': count})
            add_info = str(add_info)
            db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_qiwi')
            users_menu.update({message.from_user.id: 'enter_qiwi'})
            return send_message(message, messages.out_pay['enter_qiwi'])

    elif user.get('menu', '') in ['enter_qiwi']:
        number = text.replace(' ', '').replace('+', '').replace('-', '')
        if number:
            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'qiwi_number': number})
            answ.balance(type='pay_out', user=user, count=add_info['count_to_out_pay'], qiwi_number=number, username=message.from_user.username, out_type='QIWI')
            db_api.insert.users(user_id=user['user_id'], menu='home', add_info=str(add_info))
            users_menu.update({message.from_user.id: 'home'})
            return send_message(message, messages.out_pay['success'])
    ############ END QIWI #####################

    # ############### YAD ###########
    if text == 'Яндекс':
        obj = {}
        obj.update(messages.out_pay['ya'])
        obj['text'] = obj['text'].replace('%max_money%', str(round(user['balance'] + user['ref_balance'], 2)))
        send_message(message, obj)
        db_api.insert.users(user_id=user['user_id'], menu='out_pay_ya')
        users_menu.update({message.from_user.id: 'out_pay_ya'})
        return

    if user.get('menu', '') in ['out_pay_ya']:
        count = helpers.ifloat(text)
        if count:
            if count < settings.min_out_pay:
                return send_message(message, messages.out_pay['error_min_pay'])
            if count > user['balance'] + user['ref_balance']:
                return send_message(message, messages.out_pay['error_max_pay'])

            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'count_to_out_pay': count})
            add_info = str(add_info)
            db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_ya')
            users_menu.update({message.from_user.id: 'enter_ya'})
            return send_message(message, messages.out_pay['enter_ya'])

    elif user.get('menu', '') in ['enter_ya']:
        number = text.replace(' ', '').replace('+', '').replace('-', '')
        if number:
            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'qiwi_number': number})
            answ.balance(type='pay_out', user=user, count=add_info['count_to_out_pay'], qiwi_number=number,
                         username=message.from_user.username, out_type='YA')
            db_api.insert.users(user_id=user['user_id'], menu='home', add_info=str(add_info))
            users_menu.update({message.from_user.id: 'home'})
            return send_message(message, messages.out_pay['success'])
    ############ END QIWI #####################

    # ############### на Webmoney ###########
    if text == 'на Webmoney':
        obj = {}
        obj.update(messages.out_pay['ya'])
        obj['text'] = obj['text'].replace('%max_money%', str(round(user['balance'] + user['ref_balance'], 2)))
        send_message(message, obj)
        db_api.insert.users(user_id=user['user_id'], menu='out_pay_web')
        users_menu.update({message.from_user.id: 'out_pay_web'})
        return

    if user.get('menu', '') in ['out_pay_web']:
        count = helpers.ifloat(text)
        if count:
            if count < settings.min_out_pay:
                return send_message(message, messages.out_pay['error_min_pay'])
            if count > user['balance'] + user['ref_balance']:
                return send_message(message, messages.out_pay['error_max_pay'])

            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'count_to_out_pay': count})
            add_info = str(add_info)
            db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_web')
            users_menu.update({message.from_user.id: 'enter_web'})
            return send_message(message, messages.out_pay['enter_ya'])

    elif user.get('menu', '') in ['enter_web']:
        number = text.replace(' ', '').replace('+', '').replace('-', '')

        add_info = ast.literal_eval(user['add_info'])
        add_info.update({'qiwi_number': number})
        answ.balance(type='pay_out', user=user, count=add_info['count_to_out_pay'], qiwi_number=number,
                     username=message.from_user.username, out_type='WEB')
        db_api.insert.users(user_id=user['user_id'], menu='home', add_info=str(add_info))
        users_menu.update({message.from_user.id: 'home'})
        return send_message(message, messages.out_pay['success'])
        ############ END QIWI #####################

    if text == '📥 Пополнить':
        answr = {'text': '''Выберете способ пополнения:''',
                 'markup': [['Яндекс или Банковская карта'], ['Киви', 'Другой способ'], ['◀️ Вернуться']]}
        send_message(message, answr)

        return

    if text == 'Другой способ':
        return send_message(message, {'text': 'Если вы хотите пополнить баланс другим способом - напишите администратору @Islam_77777', 'markup': messages.start['markup']})
    if text == '📮Мои заказы':
        channels = db_api.get.channels(user_id=user['user_id'])
        posts = db_api.get.posts(user_id=user['user_id'])
        text = 'Вот ваши заказы:\n'
        if len(channels) < 1 and len(posts) < 1:
            return send_message(message, {'text': '''У вас нет заказов!⛔️
🔧🔨Чтобы добавить ваш канал для раскрутки - действуйте по инструкции, указанной выше.''', 'markup': messages.for_subs['markup']})
        else:
            if len(channels) > 0:
                for i in channels:
                    text += '✴️ Канал: {} \n💸 Стоимость: {}\n 📥 Осталось вступлений: {}\n\n'.format(i['channel_name'], i['cost'], i['views'])
            if len(posts) > 0:
                for post in posts:
                    if post['status'] in ['Edit', 'Success']:
                        continue
                    text += '''✴️ Пост: {channel} / {post} https://t.me/{channel}/{post}\n💸 Стоимость: {cost}\n📥 Осталось просмотров: {remain}\nСтатус: {status}\n\n'''.format(
                        channel=post['from_chat_username'],
                        post=post['forward_from_message_id'],
                        cost=post['cost'],
                        remain=post['remain'],
                        status=post['status']
                    )
        return send_message(message, {'text': text, 'markup': messages.for_subs['markup']})
    if text == 'Киви':
        answ.gen_code(user=user, send_message=send_message, message=message)
        return
    if text == 'Яндекс или Банковская карта':
        answ.gen_code_ya(user=user, send_message=send_message, message=message)
        return
        ##################### Вывод меню

    ########################

    if text == 'Админка':
        if message.from_user.id in settings.admins:
            db_api.insert.users(user_id=message.from_user.id, menu='admin')
            users_menu.update({message.from_user.id: 'admin'})
            send_message(message, messages.admin)
            return

    if text == 'Модерация' and user.get('menu', '').startswith('admin'):
        db_api.insert.users(user_id=message.from_user.id, menu='admin-moderation')
        users_menu.update({message.from_user.id: 'admin-moderation'})
        send_message(message, messages.admin_new['moderation'])
        return

    if text == 'Каналы' and user.get('menu', '') in ['admin-moderation']:
        tb.send_message(chat_id=message.chat.id, text='Каналы в базе:', reply_markup=answ.inline_channels(page_n=1))
        return

    if text == 'Посты' and user.get('menu', '') in ['admin-moderation']:
        tb.send_message(chat_id=message.chat.id, text='Новые посты:', reply_markup=answ.inline_posts(page_n=1))
        return

    if user.get('menu', '') in ['admin']:
        if text == 'Заявки на вывод':
            tb.send_message(chat_id=message.chat.id, text='Заявки на вывод', reply_markup=answ.inline_requests(page_n=1))
            return

        if text == 'Изменить баланс':
            db_api.insert.users(user_id=message.from_user.id, menu='enter_username')
            users_menu.update({message.from_user.id: 'enter_username'})
            send_message(message, messages.edit_balance)
            return
        if text == 'Пополнить баланс':
            db_api.insert.users(user_id=message.from_user.id, menu='enter_username_pay')
            users_menu.update({message.from_user.id: 'enter_username_pay'})
            send_message(message, messages.edit_balance)
            return
        if text == 'Сделать рассылку':
            db_api.insert.users(user_id=message.from_user.id, menu='enter_message')
            users_menu.update({message.from_user.id: 'enter_message'})
            send_message(message, messages.mailer)
            return
    elif user.get('menu', '') in ['enter_message']:
        repost_message = message
        db_api.insert.users(user_id=user['user_id'], menu='repost_message_success')
        users_menu.update({message.from_user.id: 'repost_message_success'})
        return send_message(message, messages.mailer['confirm'])
    elif user.get('menu', '') in ['repost_message_success']:
        if text == '✅ Подтвердить':
            if repost_message is not None:
                threading.Thread(target=answ.mailer, kwargs={'message': repost_message}).start()
                db_api.insert.users(user_id=message.from_user.id, menu='admin')
                users_menu.update({message.from_user.id: 'admin'})
                return send_message(message, messages.mailer['success'])

                # Просим стоимость
    elif user.get('menu', '') in ['enter_username']:
        id = helpers.ifloat(text)
        if id:
            user_to = db_api.get.users(user_id=id)
            if len(user_to) < 1:
                return send_message(message, messages.edit_balance['err_user'])
            msf = {}
            msf.update(messages.edit_balance['enter_balance'])
            msf['text'] = msf['text'].replace('%balance%', str(user_to[0]['balance']))

            send_message(message, msf)
            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'user_id': id})
            add_info = str(add_info)
            db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_balance_id')
            users_menu.update({message.from_user.id: 'enter_balance_id'})
            return
        else:
            if '@' in text:
                text = text.replace('@', '')
                user_to = db_api.get.users(username=text)
                if len(user_to) < 1:
                    return send_message(message, messages.edit_balance['err_user'])
                msf = {}
                msf.update(messages.edit_balance['enter_balance'])
                msf['text'] = msf['text'].replace('%balance%', str(user_to[0]['balance']))

                send_message(message, msf)
                add_info = ast.literal_eval(user['add_info'])
                add_info.update({'user_id': text})
                add_info = str(add_info)
                db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_balance_name')
                users_menu.update({message.from_user.id: 'enter_balance_name'})
                return
            else:
                return send_message(message, messages.edit_balance['err_user'])

    elif user.get('menu', '') in ['enter_balance_name']:
        id = helpers.ifloat(text)
        if id or id == 0.0:

            send_message(message, messages.edit_balance['success'])
            add_info = ast.literal_eval(user['add_info'])
            if isinstance(add_info['user_id'], str):
                user_id = db_api.get.users(username=add_info['user_id'])[0]['user_id']
                db_api.insert.users(user_id=user_id, balance=id)
            else:
                db_api.insert.users(user_id=add_info['user_id'], balance=id)
            db_api.insert.users(user_id=user['user_id'], menu='admin')
            users_menu.update({message.from_user.id: 'admin'})
            return
        else:
            return send_message(message, messages.edit_balance['err_number'])

    elif user.get('menu', '') in ['enter_balance_id']:
        id = helpers.ifloat(text)
        if id:

            send_message(message, messages.edit_balance['success'])
            add_info = ast.literal_eval(user['add_info'])
            db_api.insert.users(user_id=add_info['user_id'], balance=id)
            db_api.insert.users(user_id=user['user_id'], menu='admin')
            users_menu.update({message.from_user.id: 'admin'})
            return
        else:
            return send_message(message, messages.edit_balance['err_number'])
    elif user.get('menu', '') in ['enter_username_pay']:
        id = helpers.ifloat(text)
        if id:
            user_to = db_api.get.users(user_id=id)
            if len(user_to) < 1:
                return send_message(message, messages.pay_balance['err_user'])
            msf = {}
            msf.update(messages.pay_balance['enter_balance'])
            msf['text'] = msf['text'].replace('%balance%', str(user_to[0]['balance']))

            send_message(message, msf)
            add_info = ast.literal_eval(user['add_info'])
            add_info.update({'user_id': id})
            add_info = str(add_info)
            db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_balance_name_pay')
            users_menu.update({message.from_user.id: 'enter_balance_name_pay'})
            return
        else:
            if '@' in text:
                text = text.replace('@', '')
                user_to = db_api.get.users(username=text)
                if len(user_to) < 1:
                    return send_message(message, messages.pay_balance['err_user'])
                msf = {}
                msf.update(messages.pay_balance['enter_balance'])
                msf['text'] = msf['text'].replace('%balance%', str(user_to[0]['balance']))

                send_message(message, msf)
                add_info = ast.literal_eval(user['add_info'])
                add_info.update({'user_id': text})
                add_info = str(add_info)
                db_api.insert.users(user_id=user['user_id'], add_info=add_info, menu='enter_balance_name_pay')
                users_menu.update({message.from_user.id: 'enter_balance_name_pay'})
                return
            else:
                return send_message(message, messages.pay_balance['err_user'])

    elif user.get('menu', '') in ['enter_balance_name_pay']:
        id = helpers.ifloat(text)
        if id or id == 0.0:

            send_message(message, messages.pay_balance['success'])
            add_info = ast.literal_eval(user['add_info'])
            if isinstance(add_info['user_id'], str):
                user_id = db_api.get.users(username=add_info['user_id'])
                answ.balance(type='pay_in', count=id, user=user_id[0])
            else:
                user_id = db_api.get.users(user_id=add_info['user_id'])
                answ.balance(type='pay_in', count=id, user=user_id[0])

            db_api.insert.users(user_id=user['user_id'], menu='admin')
            users_menu.update({message.from_user.id: 'admin'})
            return
        else:
            return send_message(message, messages.pay_balance['err_number'])

    elif user.get('menu', '') in ['advert_enter_cost']:
        ##################
        ## Добавление поста    ###########################################
        # Просим стоимость
        cost = helpers.ifloat(text)
        if cost:
            if cost < settings.min_post_cost:
                return send_message(message, messages.for_subs['error_low_cost'])
            send_message(message, messages.for_subs['success_count'])
            add_info.update({'cost': cost})

            db_api.insert.users(user_id=user['user_id'], add_info=str(add_info), menu='advert_enter_count')
            users_menu.update({message.from_user.id: 'advert_enter_count'})
            return
        else:
            return send_message(message, messages.channel_enter_cost['error'])

    elif user.get('menu', '') in ['advert_enter_count']:
        # Просим кол-во
        count = helpers.ifint(text)
        if count:
            if count < 1:
                return
            add_info.update({'count': count})
            conf_mes = {}
            conf_mes.update(messages.for_subs['success_apply'])
            conf_mes['text'] = conf_mes['text'].format(count, add_info['cost'], count * add_info['cost'])
            send_message(message, conf_mes)

            db_api.insert.users(user_id=user['user_id'], add_info=str(add_info), menu='advert_confirm_post')
            users_menu.update({message.from_user.id: 'advert_confirm_post'})
            return

        else:
            send_message(message, messages.channel_enter_count['error_int'])
            return
    elif user.get('menu', '') in ['advert_confirm_post']:
        # Просим подтверждения
        try:
            if text == '✅ Подтвердить':
                answ.post_confirm(user, send_message, message)
                db_api.insert.users(user_id=user['user_id'], menu='home')
                users_menu.update({message.from_user.id: 'home'})
                return
            else:
                return send_message(message, messages.channel_enter_count['error'])
        except:
            return
    elif user.get('menu', '').startswith('advert-view-'):
        post = db_api.get.posts(user_id=user['user_id'], order_by='-id', _limit=1)[0]

        if user['menu'] in ['advert-view-cost']:
            # записываем стоимость за показ и записываем кол-во показов
            try:
                text = text.replace(',', '.')
                if float(text) < settings.min_view_cost:
                    return send_message(message, messages.post_enter_cost)

                post['cost'] = text
                db_api.insert.posts(**post)
                db_api.insert.users(user_id=user_id, menu='advert-view-count')
            except:
                return send_message(message, messages.post_enter_cost)
        elif user['menu'] in ['advert-view-count']:
            try:
                post['count_all'] = int(text)
            except:
                return send_message(message, messages.post_enter_count['error_int'])

            if post['count_all'] < 10:
                return send_message(message, messages.post_enter_count['error_count'])

            db_api.insert.posts(**post)
            db_api.insert.users(user_id=user_id, menu='advert-view-confirm')

            all_cost = post['count_all'] * post['cost']

            return send_message(
                message, {
                    'text': 'Ваш заказ: {} просмотров. Общая стоимость - {}р.\n\nПроверьте баланс, после подтверждения '
                            'необходимая сумма будет списана с вашего счета. Подтвердите заказ.'.format(
                        post['count_all'], all_cost),
                    'markup': [['✅ Подтверждаю'], ['⛔️ Отмена']]

                })
        elif user['menu'] in ['advert-view-confirm']:
            # проверка баланса и возможности старта
            if post['count_all'] < 10:
                return send_message(message, messages.post_enter_count['error_count'])

            all_cost = post['count_all'] * post['cost']
            if user['balance'] < all_cost:
                post['count_all'] = None
                db_api.insert.posts(**post)
                db_api.insert.users(user_id=user_id, menu='advert-view-count')

                count_wat = round(user['balance'] / post['cost'])

                return send_message(message, {
                    'text': 'Ваш баланс не позволяет заказать столько просмотров. Вы можете заказать {} просмотров. Начните заново или измените количество просмотров. '.format(
                        count_wat)})
            else:
                post['status'] = 'New'
                post['remain'] = post['count_all']
                db_api.insert.posts(**post)
                answ.balance('pay_post', user, all_cost)
                return send_message(message, messages.post_success)

        if not post.get('cost'):
            db_api.insert.users(user_id=user_id, menu='advert-view-cost')
            return send_message(message, messages.post_enter_cost)

        if not post.get('count_all'):
            db_api.insert.users(user_id=user_id, menu='advert-view-count')
            return send_message(message, messages.post_enter_count)

        # prin(post)
        pass

    # Возвращение на домашний экран
    if text == '◀️ Вернуться':
        obj = {}
        obj.update(messages.start)
        obj['text'] = random.choice(['🏠Вы вернулись в главное меню .'])
        return send_message(message, mobj=obj)
    else:
        if user['menu'] == 'advert':
            send_message(message, {'text': '''У вас нет заказов!⛔️
🔧🔨Чтобы добавить ваш канал для раскрутки - действуйте по инструкции, указанной выше.''', 'markup': messages.for_subs['markup']})


@tb.message_handler(content_types=["contact"])
def contact(message):
    text = message.text
    user = get_user(message.from_user.id, message)
    if not user:
        return

    if user['menu'] == 'enter_qiwi':
        add_info = ast.literal_eval(user['add_info'])
        add_info.update({'qiwi_number': message.contact.phone_number})
        answ.balance(type='pay_out', user=user, count=add_info['count_to_out_pay'], qiwi_number=message.contact.phone_number, username=message.from_user.username)
        db_api.insert.users(user_id=user['user_id'], menu='home', add_info=str(add_info))
        users_menu.update({message.from_user.id: 'home'})
        return send_message(message, messages.out_pay['success'])


@tb.callback_query_handler(lambda query: True)
def inl(query):
    data = query.data
    user = get_user(query.from_user.id, query.message)

    if not user:
        return
    
    if data.startswith('declinec-'):
        channel = data.split('-', 1)[1]
        db_api.delete.channels(channel_name=channel)
        return tb.edit_message_text(text='Удален', chat_id=query.message.chat.id, message_id=query.message.message_id)

    elif data.startswith('acceptcid-'):
        channel = data.split('-', 1)[1]
        db_api.insert.channels(channel_name=channel, mod=1)
        return tb.edit_message_text(text='Принят', chat_id=query.message.chat.id, message_id=query.message.message_id)

    elif data.startswith('acceptid_'):
        db_api.insert.transactions(trans_id=int(data.split('_')[1]), status='done')
        return tb.edit_message_text(text='Заявка принята', chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=answ.inline_requests(1))

    elif data.startswith('decline_'):
        tr = db_api.get.transactions(trans_id=int(data.split('_')[1]))
        user = db_api.get.users(user_id=tr[0]['user_id'])
        if len(user) > 0:
            db_api.insert.users(user_id=tr[0]['user_id'], balance=user[0]['balance'] + tr[0]['count'])
        db_api.insert.transactions(trans_id=int(data.split('_')[1]), status='decline')
        return tb.edit_message_text(text='Заявка отклонена', chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=answ.inline_requests(1))

    elif data.startswith('ban_'):
        #logger.info("Line 903: " + data)  #***
        id = data.split('_')[1]
        users = bans[id]
        for i in users:
            db_api.insert.ban_channels(channel_name=str(i))
        db_api.insert.transactions(trans_id=int(data.split('_')[1]), status='done')
        tb.send_message(chat_id=query.message.chat.id, text='Забанены')
        return

    elif data.startswith('tid_'):
        tr = db_api.get.transactions(trans_id=int(data.split('_')[1]))[0]
        text = '''Пользователь: @{}
id: {}
Номер {}: {}
Сумма для вывода: {}
Дата: {}'''.format(tr['username'], tr['user_id'], tr['menu'], tr['qiwi_number'], tr['count'], tr['date'])

        return tb.edit_message_text(text=text, chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=answ.gen_inl(
            [[{'text': '✅ Принять', 'data': 'acceptid_{}'.format(tr['trans_id'])}, {'text': '❌ Отклонить', 'data': 'decline_{}'.format(tr['trans_id'])}]]))

    elif data.startswith('pgn_'):
        # prin(data)
        return tb.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=answ.inline_requests(int(data.replace('pgn_', ''))))

    elif data == 'cancel_check_admin':
        tb.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
        db_api.insert.users(user_id=query.message.from_user.id, menu='home')
        users_menu.update({query.from_user.id: 'home'})
        return send_message(query.message, messages.decline)

    elif data == 'check_admin':
        add_info = ast.literal_eval(user['add_info'])
        if 'channel_name' in add_info:   #***
            admin = answ.chechk_admin(add_info['channel_name'], bot_info.username)
        else:
            admin = None
        if admin:
            send_message(query.message, messages.for_subs['success'])

            db_api.insert.users(user_id=query.from_user.id, menu='advert_enter_cost')
            return
        else:
            tb.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
            tb.send_message(text='Всё еще не администратор', chat_id=query.message.chat.id, reply_markup=answ.gen_inl(messages.for_subs['error_not_admin']['markup']))
            return

    elif data.startswith('chck-public-'):
        channel = data.split('-')[2]
        answ.check_sub(channel, user, send_message, query.message)
        return

    elif data.startswith('cid-'):
        ch = db_api.get.channels(channel_name=data.split('-')[1])[0]
        pg = data.split('-')[2]
        if ch['mod'] == 1:
            mark = answ.gen_inl([[{'text': '◀️', 'data': 'pgnс_{}'.format(pg)}],
                                 [{'text': '❌ Удалить',
                                   'data': 'declinec-{}'.format(ch['channel_name'])}]])
        else:
            mark = answ.gen_inl([[{'text': '◀️', 'data': 'pgnс_{}'.format(pg)}],
                                 [{'text': '✅ Принять', 'data': 'acceptcid-{}'.format(ch['channel_name'])},
                                  {'text': '❌ Удалить',
                                   'data': 'declinec-{}'.format(ch['channel_name'])}]])

        text = '''Канал: [{}](https://t.me/{})
[Заказчик](tg://user?id={})
Подписчиков осталось: {}
Стоимость подписки: {}
'''.format(ch['channel_name'], ch['channel_name'].replace('@', ''), ch['user_id'], ch['views'], ch['cost'])
        try:
            return tb.edit_message_text(text=text, chat_id=query.message.chat.id, message_id=query.message.message_id,
                                        reply_markup=mark, parse_mode='Markdown')
        except:
            text = '''Канал: [{}](https://t.me/{})
Заказчик {}
Подписчиков осталось: {}
Стоимость подписки: {}
            '''.format(ch['channel_name'], ch['channel_name'].replace('@', ''), ch['user_id'], ch['views'], ch['cost'])
            return tb.edit_message_text(text=text, chat_id=query.message.chat.id, message_id=query.message.message_id,
                                        reply_markup=mark, parse_mode='Markdown')

    elif data.startswith('pgnс_'):
        return tb.edit_message_text(chat_id=query.message.chat.id, message_id=query.message.message_id, text='Меню вывода',
                                    reply_markup=answ.inline_channels(int(data.replace('pgnс_', ''))))

    elif data.startswith('pgn_'):
        return tb.edit_message_text(chat_id=query.message.chat.id, message_id=query.message.message_id, text='Меню вывода',
                                    reply_markup=answ.inline_requests(int(data.replace('pgn_', ''))))

    elif data.startswith('autoidq_'):
        tr = db_api.get.transactions(trans_id=int(data.split('_')[1]))[0]
        number = helpers.check_number(tr['qiwi_number'])
        pg = data.split('_')[2]
        pay_result = qiwi.make_payment(round(tr['count'], 2), number)
        if pay_result[0]:

            if pay_result[1]['transaction']['state']['code'] == 'Accepted':
                db_api.insert.transactions(trans_id=tr['trans_id'], status='done')

                return tb.edit_message_text(text='✅ успешно!', chat_id=query.message.chat.id, message_id=query.message.message_id,
                                            reply_markup=answ.gen_inl([[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))
            else:
                return tb.edit_message_text(text='⚠️ {}'.format(pay_result[1]['transaction']['state']['code']), chat_id=query.message.chat.id, message_id=query.message.message_id,
                                            reply_markup=answ.gen_inl([[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))
        else:
            return tb.edit_message_text(text='⛔️ {}'.format(pay_result[1]),
                                        chat_id=query.message.chat.id, message_id=query.message.message_id,
                                        reply_markup=answ.gen_inl([[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))

    elif data.startswith('autoidy_'):
        tr = db_api.get.transactions(trans_id=int(data.split('_')[1]))[0]
        pg = data.split('_')[2]
        pay_result = wallet.request_payment({'pattern_id': 'p2p', 'to': tr['qiwi_number'], 'amount': tr['count'], 'comment': settings.out_comment, 'message': settings.out_comment})
        if pay_result['status'] == 'success':
            pay_result = wallet.process_payment({'request_id': pay_result['request_id']})
            if pay_result['status'] == 'success':
                db_api.insert.transactions(trans_id=tr['trans_id'], status='done')

                return tb.edit_message_text(text='✅ успешно!', chat_id=query.message.chat.id,
                                            message_id=query.message.message_id,
                                            reply_markup=answ.gen_inl(
                                                [[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))
            else:
                return tb.edit_message_text(text='⚠️ {}'.format(pay_result['error_description']),
                                            chat_id=query.message.chat.id, message_id=query.message.message_id,
                                            reply_markup=answ.gen_inl(
                                                [[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))
        else:
            return tb.edit_message_text(text='⛔️ {}'.format(pay_result['error_description']),
                                        chat_id=query.message.chat.id, message_id=query.message.message_id,
                                        reply_markup=answ.gen_inl(
                                            [[{'text': '◀️', 'data': 'pgn_{}'.format(pg)}]]))

            # except:
    #     return

    elif data.startswith('post-mod_'):
        post_id = data.split('_')[1]
        post = db_api.get.posts(id=int(post_id), _limit=1)[0]
        pg = data.split('_')[2]
        try:
            tb.forward_message(
                chat_id=query.message.chat.id,
                from_chat_id=post['user_id'],
                message_id=post['forward_from_message_id']
            )
        except Exception as e:
            #AS prin(e)
            logger.error(str(e))
            tb.send_message(
                chat_id=query.message.chat.id,
                text='Невозможно переслать сообщение, возможно его удалалили.'
            )
        mark = answ.gen_inl([[
            {'text': '✅ Принять', 'data': 'acceptpost-{}'.format(post_id)},
            {'text': '❌ Заблокировать', 'data': 'blockpost-{}'.format(post_id)}
        ]])

        cost_finish = 0
        try:
            cost_finish = post['cost'] * post['count_all']
        except:
            pass
        text_mess = '''Репост c канала {ch} - https://t.me/{ch}/{ch_id}
[Заказчик](tg://user?id={author} )
Количество просмотров : {views}
Общая стоимость: {cost}
        '''.format(
            ch=post['from_chat_username'],
            ch_id=post['forward_from_message_id'],
            author=post['user_id'],
            views=post['count_all'],
            cost=cost_finish
        )
        return tb.edit_message_text(text=text_mess, chat_id=query.message.chat.id, message_id=query.message.message_id,
                                    reply_markup=mark, parse_mode='Markdown')

    elif data.startswith('acceptpost-'):
        post_id = data.split('-')[1]
        post = db_api.get.posts(id=int(post_id))[0]
        post['status'] = 'Active'
        db_api.insert.posts(**post)
        return tb.edit_message_text(text='Одобрено', chat_id=query.message.chat.id, message_id=query.message.message_id)

    elif data.startswith('blockpost-'):
        post_id = data.split('-')[1]
        post = db_api.get.posts(id=int(post_id))[0]
        post['status'] = 'Blocked'
        db_api.insert.posts(**post)
        return tb.edit_message_text(text='Заблокировано', chat_id=query.message.chat.id, message_id=query.message.message_id)


app = flask.Flask(__name__)


# Empty webserver index, return nothing, just http 200
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return ''


# Process webhook calls
@app.route(settings.WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if flask.request.headers.get('content-type') == 'application/json':
        json_string = flask.request.get_data().decode('utf-8')
        # prin(json_string)
        update = types.Update.de_json(json_string)
        tb.process_new_updates([update])
        return ''
    else:
        flask.abort(403)


@app.route('/ya_pay', methods=['POST', 'GET'])
def ymon():
    token = api.Wallet.get_access_token(client_id='11488C85A286C555F038E5BEEB40D7145D33895ED6E68ECC68C07DBEDFA920B7', code=flask.request.args['code'],
                                        redirect_uri='https://194.87.237.18:8443/ya_pay')['access_token']

    return token


# @app.route('/ya_notif',methods=['POST','GET'])
# def ya():
#     params = flask.request.form
#     prin(flask.request.form)
#     if len(params)>0:
#         if params['operation_id']!='test-notification':
#             operation = wallet.operation_details(operation_id=params['operation_id'])
#             if operation['status']=='success' and operation['direction']=='in':
#                 if 'message' in operation:
#                     answ.check_code(code=operation['message'],count=operation['amount'],send_message=send_message,number=operation['operation_id'])
#                 elif 'comment' in operation:
#                     answ.check_code(code=operation['comment'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#                 elif 'details' in operation:
#                     answ.check_code(code=operation['details'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#                 elif 'title' in operation:
#                     answ.check_code(code=operation['title'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#         else:
#             operation = wallet.operation_details(operation_id='1122570744402048017')
#             prin(operation)
#             if operation['status']=='success' and operation['direction']=='in':
#                 if 'message' in operation:
#                     answ.check_code(code=operation['message'],count=operation['amount'],send_message=send_message,number=operation['operation_id'])
#                 elif 'comment' in operation:
#                     answ.check_code(code=operation['comment'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#                 elif 'details' in operation:
#                     answ.check_code(code=operation['details'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#                 elif 'title' in operation:
#                     answ.check_code(code=operation['title'], count=operation['amount'], send_message=send_message, number=operation['operation_id'])
#
#
#
#     return "OK",200
# if flask.request.headers.get('content-type') == 'application/json':
#     json_string = flask.request.get_data().decode('utf-8')
#     update = telebot.types.Update.de_json(json_string)
#     tb.process_new_updates([update])
#     return ''
# else:
#     flask.abort(403)


# Remove webhook, it fails sometimes the set if there is a previous webhook

logger.info(tb.remove_webhook())
time.sleep(4)
# # # Set webhook
s = settings.WEBHOOK_URL_BASE + settings.WEBHOOK_URL_PATH
logger.info(s)
logger.info(tb.set_webhook(url=s,
                certificate=open(settings.WEBHOOK_SSL_PRIV, 'r'),allowed_updates=['update_id','message','edited_message','channel_post','edited_channel_post','inline_query','chosen_inline_result','callback_query','shipping_query','pre_checkout_query']))


threading.Thread(target=answ.check_qiwi,kwargs={'send_message':send_message}).start()
threading.Thread(target=answ.check_ya,kwargs={'send_message':send_message}).start()

log = logging.getLogger('werkzeug')
#log.setLevel(logging.DEBUG)
log.setLevel(logging.WARNING)

app.run(host=settings.WEBHOOK_LISTEN,
        port=settings.WEBHOOK_PORT,
#	debug=True,
#        ssl_context=(settings.WEBHOOK_SSL_CERT, settings.WEBHOOK_SSL_PRIV),
#        ssl_context=(settings.WEBHOOK_SSL_PRIV, settings.WEBHOOK_SSL_CERT),
        threaded=True)

