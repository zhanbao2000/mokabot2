import nonebot
from nonebot import on_command
from nonebot.adapters import Bot
from nonebot.adapters.cqhttp import MessageEvent

from public_module.mb2pkg_database import QQ
from public_module.mb2pkg_mokalogger import Log
from .exceptions import *

match_arc_bind = on_command('arc绑定', priority=5)
match_arc_bind_username = on_command('arc绑定用户名', priority=5)

log = Log(__name__).getlog()

superusers = nonebot.get_driver().config.superusers
ARC_RESULT_LIST = ['bandori', 'guin', 'moe']


@match_arc_bind.handle()
async def arc_bind_handle(bot: Bot, event: MessageEvent):
    userid = str(event.get_message()).strip()

    try:  # TODO 绑定的时候为用户提示一次好友名，以免填写错
        arc_bind_userid(event.user_id, userid)
        msg = f'关联完成！已将QQ<{event.user_id}>关联至Arc好友码<{userid}>'
    except InvalidUserIdError as e:
        msg = f'{e}：只能绑定纯数字9位好友码'
        log.warn(msg)

    await bot.send(event, msg)


@match_arc_bind_username.handle()
async def arc_bind_username_handle(bot: Bot, event: MessageEvent):
    username = str(event.get_message()).strip()
    user_id = event.user_id
    arc_bind_username(user_id, username)

    myqq = QQ(user_id)

    msg = f'关联完成！已将QQ<{user_id}>关联至Arc用户名<{username}>，请等待管理员为查询用账号添加好友，' \
          f'若您在2021年7月之前已经绑定过好友码，那您无需等待管理员添加您到查分器好友列表中\n' \
          f'注意：变更用户名后需要重新绑定用户名'
    await bot.send(event, msg)
    msg = f'收到新的arc用户名绑定（用户名:{myqq.arc_friend_name}，好友码:{myqq.arc_friend_id}，QQ:{user_id}），请记得加好友'
    for _user_id in superusers:
        await bot.send_private_msg(user_id=_user_id, message=msg)


def arc_bind_userid(qq: int, userid: str) -> None:
    myqq = QQ(qq)

    if userid.isdigit() and len(userid) == 9:
        myqq.arc_friend_id = userid
        log.info(f'已将QQ<{qq}>和Arcaea好友码<{userid}>成功绑定')
    else:
        raise InvalidUserIdError(userid)


def arc_bind_username(qq: int, username: str) -> None:
    myqq = QQ(qq)

    myqq.arc_friend_name = username
    log.info(f'已将QQ<{qq}>和Arcaea用户名<{username}>成功绑定')