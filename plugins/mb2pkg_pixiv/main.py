import asyncio
import base64
import os

import nonebot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pixivpy_async import AppPixivAPI

from .config import Config

from public_module.mb2pkg_mokalogger import Log

log = Log(__name__).getlog()

temp_absdir = nonebot.get_driver().config.temp_absdir
PIXIV_ACT = Config().pixiv_username
PIXIV_PWD = Config().pixiv_password
relogin_time = Config().relogin_time

Pixiv = AppPixivAPI()

scheduler = AsyncIOScheduler()


@scheduler.scheduled_job('interval', minutes=relogin_time)
async def _init_pixiv():
    global Pixiv
    if Pixiv.refresh_token is None:
        login_json = await Pixiv.login(PIXIV_ACT, PIXIV_PWD)
        log.info('Pixiv初始化成功')
        log.debug(str(login_json))
    else:
        login_json = await Pixiv.login(refresh_token=Pixiv.refresh_token)
        log.info('Pixiv重新登陆成功')
        log.debug(str(login_json))


async def pixiv_mokabot_api(api_method, **kwargs):
    global Pixiv
    result = None

    log.info('PixivAPI处理：method:{}, params:{}'.format(api_method, kwargs))

    try:
        if api_method == 'illust_detail':
            result = await Pixiv.illust_detail(**kwargs)
            # return: see https://github.com/upbit/pixivpy/wiki/Sniffer-for-iOS-6.x---Common-API#%E7%94%A8%E6%88%B7---%E6%8F%92%E7%94%BB%E5%88%97%E8%A1%A8
        elif api_method == 'user_detail':
            result = await Pixiv.user_detail(**kwargs)
            # return: see https://github.com/upbit/pixivpy/wiki/Sniffer-for-iOS-6.x---Common-API#%E7%94%A8%E6%88%B7---%E8%AF%A6%E6%83%85
        elif api_method == 'illust_ranking':
            result = await Pixiv.illust_ranking(**kwargs)
            # return: see https://github.com/upbit/pixivpy/wiki/Sniffer-for-iOS-6.x---Search-Tab#%E6%90%9C%E7%B4%A2---%E5%B0%91%E5%A5%B3
        elif api_method == 'search_illust':
            result = await Pixiv.search_illust(**kwargs)
            # return: see https://github.com/upbit/pixivpy/wiki/Sniffer-for-iOS-6.x---Search-Tab#%E6%90%9C%E7%B4%A2---%E5%B0%91%E5%A5%B3
        elif api_method == 'download':
            url = kwargs['url']
            await Pixiv.download(url=url, path=temp_absdir, name=os.path.basename(url))
            savepath = os.path.join(temp_absdir, os.path.basename(url))
            log.info('下载完成：保存路径：{}'.format(savepath))
            pic_b64 = base64.b64encode(open(savepath, 'rb').read()).decode()
            result = {'format': os.path.splitext(savepath)[1][1:], 'image': pic_b64}
            # return: {'format': 后缀名..., 'image': b64编码图像...}
        assert result
    except Exception as e:
        log.exception(e)
        result = str(e)

    return result


loop = asyncio.get_event_loop()
loop.run_until_complete(_init_pixiv())
scheduler.start()
