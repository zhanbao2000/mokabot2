import asyncio
import base64
import os
import time
from io import BytesIO

import aiofiles
import aiohttp
import nonebot
from PIL import Image, ImageOps
from nonebot import permission as su
from nonebot import require, on_command
from nonebot.adapters import Bot
from nonebot.adapters.cqhttp import MessageSegment, GroupMessageEvent, permission
from selenium import webdriver

from public_module.mb2pkg_database import Group
from public_module.mb2pkg_mokalogger import getlog
from public_module.mb2pkg_public_plugin import get_time
from .config import Config

scheduler = require('nonebot_plugin_apscheduler').scheduler

match_enable_notice = on_command('关闭国服公告',
                                 aliases={'关闭日服公告', '开启国服公告', '开启日服公告'},
                                 priority=5,
                                 permission=su.SUPERUSER | permission.GROUP_ADMIN | permission.GROUP_OWNER,)

log = getlog()

temp_absdir = nonebot.get_driver().config.temp_absdir
env = nonebot.get_driver().config.environment
firefox_binary_location = nonebot.get_driver().config.firefox_binary_location
JPBUG = os.path.join(Config().bandori_server_info, 'jp/bug')
JPNOTICE = os.path.join(Config().bandori_server_info, 'jp/notice')
CNNOTICE = os.path.join(Config().bandori_server_info, 'cn/notice')


@match_enable_notice.handle()
async def enable_notice_handle(bot: Bot, event: GroupMessageEvent):
    if isinstance(event, GroupMessageEvent):
        group_id = event.group_id
        mygroup = Group(group_id)

        news_xx = 'news_jp' if '日服' in event.raw_message else 'news_cn'
        enable = '1' if '开启' in event.raw_message else '0'
        mygroup.__setattr__(news_xx, enable)

        msg = f'已{event.raw_message}，群组<{group_id}>的设置{news_xx}已设为{enable}'
        log.info(msg)

        await bot.send(event, msg)


@scheduler.scheduled_job('cron', minute='1, 11, 21, 31, 41, 51')
async def job_send_game_notice():
    start = time.time()
    bot_dict = nonebot.get_bots()
    bot: Bot = list(bot_dict.values())[0]
    try:
        groups = await bot.get_group_list()
        log.debug(groups)

        for XX, news_xx, Xfu, notices in [
            ('JP', 'news_jp', '日', await check_notice_update('JP')),
            ('CN', 'news_cn', '国', await check_notice_update('CN'))
        ]:
            # 如果列表非空则发
            if notices:
                for group in groups:
                    group_id = group['group_id']
                    mygroup = Group(group_id)
                    if mygroup.__getattr__(news_xx) == '1':
                        for notice in notices:
                            msg = f'{Xfu}服新公告\n' \
                                  f'标题：{notice["title"]}\n' \
                                  f'时间：{notice["time"]}\n' + \
                                  MessageSegment.image(file=f'file:///{notice["savepath"]}')
                            try:  # 防止被禁言后无法继续发
                                await bot.send_group_msg(group_id=group_id, message=msg)
                            except Exception as senderror:
                                log.error(f'发往<{group_id}>时发送失败，原因：{senderror}')
                            await asyncio.sleep(1)
                        await asyncio.sleep(10)
                    # else:
                    # 绕过log，因为群组太多
                    #     log.warn(f'{group_id}设置{news_xx}参数为0或未设置，取消该群组发送{Xfu}服公告')

    except Exception as e:
        log.exception(e)

    log.info('定时任务已处理完成 耗时%.3fs' % (time.time() - start))


async def check_notice_update(server: str) -> list[dict[str, str]]:
    """
    检查对应服务器是否有公告更新，

    :param server: 目标服务器，仅可选'JP'或'CN'
    :return: [{'title': 活动标题, 'time': 发布时间, 'savepath': 保存绝对路径}, ...]，无需更新时返回空数组，可以等价于False
    """
    result = []

    # 判断需要处理的服务器类型
    # 注意，日服国服的处理方式不完全相同，详见代码
    if server == 'JP':

        # 分别从本地和远程查看日服（活动）公告最大order
        # connector=aiohttp.TCPConnector(verify_ssl=False)  采用一个禁用SSL验证的连接器来避免服务器端报SSL错误
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.get(url='https://api.star.craftegg.jp/api/information', timeout=10) as r:
                # 从网页获取json
                r.encoding = 'utf-8'
                notice_json = await r.json()
                remote_order = notice_json['NOTICE'][0]['viewOrder']
                log.debug('从craftegg_api获取到了公告')
                log.debug(f'远程日服（活动）公告最大order为：{remote_order}')
        async with aiofiles.open(JPNOTICE, mode='r') as f:
            local_order = int(await f.read())
            log.debug(f'本地记录的日服（活动）公告最大order为：{local_order}')

        # 下面算法解释：i代表新增的公告数量，若新公告order为1872、1871、1868、1860、1845...，本地最大order为1860，则i=3
        # i=3，即获取数组中的第0、1、2个公告，即order为1872、1871、1868的公告
        if remote_order > local_order:
            i = 0
            while notice_json['NOTICE'][i]['viewOrder'] > local_order:
                i += 1
            while i - 1 >= 0:
                obj = notice_json['NOTICE'][i - 1]
                notice_title = f'{obj["informationType"]} {obj["title"]}'
                notice_time = get_time('%Y-%m-%d %H:%M:%S', obj['viewStartAt'] / 1000) + ' (UTC+8)'
                savepath = capture(f'https://web.star.craftegg.jp/information/{obj["linkUrl"]}', obj['linkUrl'])
                log.info(f'获取到新的公告，标题：{notice_title}，时间：{notice_time}')
                result.append({'title': notice_title, 'time': notice_time, 'savepath': savepath})
                i -= 1
            # 修改本地数值
            async with aiofiles.open(JPNOTICE, mode='w') as f:
                await f.write(str(remote_order))
                log.info(f'本地日服（活动）公告最大order已修改为：{remote_order}')

        # 分别从本地和远程查看日服（BUG）公告最大order
        remote_order = notice_json['BUG'][0]['viewOrder']
        log.debug(f'远程日服（BUG）公告最大order为：{remote_order}')
        async with aiofiles.open(JPBUG, mode='r') as f:
            local_order = int(await f.read())
            log.debug(f'本地记录的日服（BUG）公告最大order为：{local_order}')

        if remote_order > local_order:
            i = 0
            while notice_json['BUG'][i]['viewOrder'] > local_order:
                i += 1
            while i - 1 >= 0:
                obj = notice_json['BUG'][i - 1]
                notice_title = f'{obj["informationType"]} {obj["title"]}'
                notice_time = get_time('%Y-%m-%d %H:%M:%S', obj['viewStartAt'] / 1000) + ' (UTC+8)'
                savepath = capture(f'https://web.star.craftegg.jp/information/{obj["linkUrl"]}', obj['linkUrl'])
                log.info(f'获取到新的公告，标题：{notice_title}，时间：{notice_time}')
                result.append({'title': notice_title, 'time': notice_time, 'savepath': savepath})
                i -= 1
            # 修改本地数值
            async with aiofiles.open(JPBUG, mode='w') as f:
                await f.write(str(remote_order))
                log.info(f'本地日服（BUG）公告最大order已修改为：{remote_order}')

    elif server == 'CN':

        # 分别从本地和远程查看国服公告最大时间戳
        async with aiofiles.open(CNNOTICE, mode='r') as f:
            local_order = int(await f.read())
            log.debug(f'本地记录的国服公告最大order为：{local_order}')
        async with aiohttp.ClientSession() as session:
            async with session.get(url='https://l3-prod-all-web-bd.bilibiligame.net/web/notice/list', timeout=10) as r:
                # 从网页获取json
                r.encoding = 'utf-8'
                notice_json = await r.json()
                log.debug('从bilibiligame获取到了公告')
                remote_order = 0
                ids = []
                # 列表ids用于记录notice_json中第几个的时间比local_order大
                for i in range(len(notice_json)):
                    t = int(time.mktime(time.strptime(notice_json[i]['startTime'][:19], '%Y-%m-%dT%H:%M:%S')))
                    # 更新remote_order，最后让他变成远程的最大值
                    remote_order = max(remote_order, t)
                    if t > local_order:
                        ids.append(i)
                log.debug(f'远程国服公告最大order为：{remote_order}')
        if remote_order > local_order:
            for item in ids:
                obj = notice_json[item]
                notice_title = obj['title']
                notice_time = time.strftime('%Y-%m-%d %H:%M:%S', time.strptime(obj['startTime'][:19], '%Y-%m-%dT%H:%M:%S')) + ' (UTC+8)'
                # 处理国服周年期间出现的空标题，仅图片公告
                if notice_title:
                    savepath = capture(f'https://l3-prod-all-web-bd.bilibiligame.net/static/webview/information/{obj["path"]}', obj['path'])
                    log.info(f'获取到新的公告，标题：{notice_title}，时间：{notice_time}')
                    result.append({'title': notice_title, 'time': notice_time, 'savepath': savepath})
                else:
                    log.warn('无头公告，不处理')
                # 修改本地数值
            async with aiofiles.open(CNNOTICE, mode='w') as f:
                await f.write(str(remote_order))
                log.info(f'本地国服公告最大order已修改为：{remote_order}')

    else:
        return []
    return result


def capture(url: str, filename: str) -> str:
    """
    对指定url生成网页截图，保存至文件

    :param url: 目标url
    :param filename: 保存文件名
    :return: 保存图片路径
    """

    if env == 'dev':

        options = webdriver.FirefoxOptions()
        options.binary_location = r"C:\Program Files\Mozilla Firefox\firefox.exe"
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        driver = webdriver.Firefox(firefox_options=options)

    else:  # 在mokabot服务器上使用linux下的chrome

        # 设置首选项，指定Chrome位置，设置无头模式（以确保截取全屏）
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')  # Running as root without --no-sandbox is not supported <- LinuxSSH上号特色

        # 以刚才的首选项创建webdriver对象
        driver = webdriver.Chrome(chrome_options=options)

    # 设置网页加载超时30秒
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)

    # 设置网页浏览器尺寸（实则渲染图片的尺寸），需要10000这样巨大的长度是为了防止页面加载不全，后续去白边交给PIL
    driver.set_window_size(700, 10000)

    # 加载网页
    driver.get(url)

    # 执行一个缩放脚本，以确保文字能够看清晰
    driver.execute_script('document.body.style.zoom="1.3"')

    # 图片渲染为base64字符串，传入PIL进行去白边
    img_b64 = driver.get_screenshot_as_base64()
    driver.close()

    image = Image.open(BytesIO(base64.b64decode(img_b64))).convert('RGB')
    # getbbox实际上检测的是黑边，所以要先将image对象反色
    ivt_image = ImageOps.invert(image)

    cropped_image = image.crop(ivt_image.getbbox())

    savepath = os.path.join(temp_absdir, f'{filename}.jpg')
    cropped_image.save(savepath)

    return savepath
