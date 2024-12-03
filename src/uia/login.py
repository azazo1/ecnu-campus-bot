"""
半自动化登录 ecnu 统一认证.
"""
from __future__ import annotations

import base64
import io
import tempfile
import traceback
from typing import Optional, Callable, Sequence, Any, Self, Type, TypeVar

from pyzbar import pyzbar
from PIL import Image
import textwrap
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from seleniumwire.webdriver import Edge, EdgeOptions

from src.config import logger, requires_init

# ECNU 统一登陆界面的使用二维码登录按钮.
QRCODE_BUTTON = '#login-content-right > div.codeBrushing.qr'
QRCODE_IMG = '#login-content-right > app-login-auth-panel > div > div.content-top > app-login-by-corp-wechat-qr > div > div > div.qrcodeImgStyle > rg-page-qr-box > div > img'
# 图书馆网页中左侧的全部展开按钮.
EXPAND_ALL_SPAN = '#SeatScreening > div:nth-child(1) > div.content > div > div.header > div.extend > p > span'
# 图书馆网页中左侧的普陀校区筛选按钮.
PUTUO_DISTRICT_SPAN = '#SeatScreening > div:nth-child(1) > div.content > div > div.filterCon > div > div:nth-child(1) > div.van-collapse-item__wrapper > div > div > div.selectItem > span'

EXTRACT_QRCODE_JS = f"""
let qrcode_img = document.querySelector("{QRCODE_IMG}");
let canvas = document.createElement('canvas');
let ctx = canvas.getContext('2d');

canvas.width = qrcode_img.width;
canvas.height = qrcode_img.height;

ctx.drawImage(qrcode_img, 0, 0, canvas.width, canvas.height);
return canvas.toDataURL('image/png');
"""

EXTRACT_QRCODE_SRC_JS = f"""
let qrcode_img = document.querySelector("{QRCODE_IMG}");
return qrcode_img.src;
"""

# title, img, url; 提供一个可用的 HTML 模板, 用于可用于邮件提醒.
QRCODE_HTML = """<!DOCTYPE html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
</head>
<body>
<div>Scan the qrcode below to login ECNU.</div>
<img src="{img}" alt="qrcode image here."/>
<div>Or open this url in wechat:</div>
<div>{url}</div>
</body>
</html>
"""
UPDATED_QRCODE_TITLE = "ECNU Login QRCode Updated"
FIRST_QRCODE_TITLE = "Login to ECNU"


class LoginError(Exception):
    """登录缓存失效时触发."""

    def __init__(self, msg: str = ""):
        super().__init__(msg)


class LibCache:
    """图书馆 quickSelect api 的必须登录缓存."""

    def __init__(self, authorization: str, cookies: dict):
        """
        :param authorization: 认证字符串.
        :param cookies: seat-lib.ecnu.edu.cn 域名的 cookies, 以 name-value 对储存.
        """
        self.authorization = authorization
        self.cookies = cookies.copy()

    def __repr__(self):
        # 使用安全的方式展示 authorization 和 cookies，避免内容过长或敏感信息暴露
        auth_display = textwrap.shorten(self.authorization, width=10)
        cookies_display = {k: textwrap.shorten(v, 10) for k, v in self.cookies.items()}

        return f"LibCache(authorization='{auth_display}', cookies={cookies_display})"

    @classmethod
    def grab_from_driver(cls, driver: Edge, timeout: float = 24 * 60) -> Self:
        """从 WebDriver 中获取 LibCache, 需要 driver 处于 ECNU 登录状态"""
        driver.get("https://seat-lib.ecnu.edu.cn/h5/#/SeatScreening/1")  # 进入图书馆选座界面, 网站会自动请求座位列表.
        # 等待图书馆网页加载完成.
        logger.debug("library site waiting for page loading...")
        WebDriverWait(driver, timeout).until(
            EC.url_matches("https://seat-lib.ecnu.edu.cn/")
        )
        # 全部展开后按左侧的普陀校区筛选按钮确保网页发送 quickSelect 请求.
        click_element(driver, EXPAND_ALL_SPAN, timeout)
        click_element(driver, PUTUO_DISTRICT_SPAN, timeout)

        req = driver.wait_for_request("quickSelect", 60)
        c = {}
        for cookie in driver.get_cookies():
            c[cookie["name"]] = cookie["value"]
        logger.info("got library login cache.")
        return cls(req.headers["authorization"], c)


class PortalCache:
    def __init__(self, authorization: str):
        self.authorization = authorization

    def __repr__(self):
        auth_display = textwrap.shorten(self.authorization, width=10)
        return f"PortalCache(authorization='{auth_display}')"

    @classmethod
    def grab_from_driver(cls, driver: Edge, timeout: float = 24 * 60) -> Self:
        driver.get("https://portal2023.ecnu.edu.cn/portal/home")
        logger.debug("portal site waiting for page loading...")
        WebDriverWait(driver, timeout).until(
            EC.url_matches("https://portal2023.ecnu.edu.cn/")
        )
        req = driver.wait_for_request("calendar-new", 60)
        logger.info(f"got portal login cache.")
        return cls(req.headers['Authorization'])


T = TypeVar("T")


class LoginCache:
    def __init__(self):
        self.cache = {}

    def add_cache(self, cache: T):
        """将某个类型的 Cache 添加进集合, 同一类型的 Cache 会相互挤占"""
        self.cache[type(cache)] = cache

    def get_cache(self, cache_cls: Type[T]) -> T | None:
        """
        通过类型来获取对应的 Cache.

        Parameters:
            cache_cls: Cache 对象的类型.

        Examples:

        >>> LoginCache().get_cache(PortalCache)
        None
        """
        return self.cache.get(cache_cls)

    def __repr__(self):
        return f"LoginCache{list(self.cache.values())}"


def click_element(driver: Edge, selector: str, timeout: float = 10):
    """
    在 driver 中点击元素, 如果元素不存在, 那么等待一段时间.
    :param driver: driver.
    :param selector: 要点击元素的 css selector.
    :param timeout: 等待元素出现要的时间.
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )
    driver.execute_script(f"""
    let ele = document.querySelector({repr(selector)});
    ele.click();
    """)


def attribute_changes(css_selector: str, attribute_name: str):
    """
    Expected Conditions 方法.

    一个元素的属性发生变化时触发.

    :param css_selector: 对应元素的 css selector, 如果其包含多个元素, 那么只会取第一个元素.
    :param attribute_name: 要监视的元素属性, 如 <img> 元素的 src 属性.
    """
    prev = None

    def _predicate(driver: EC.WebDriverOrWebElement):
        nonlocal prev
        ele = driver.find_element(By.CSS_SELECTOR, css_selector)
        new = ele.get_attribute(attribute_name)
        if prev is None:
            prev = new
        elif prev != new:
            prev = new
            return True
        return False

    return _predicate


def _wait_qrcode_update_or_login(driver: Edge, timeout: float) -> bool:
    """
    等待用户成功登录或者登录二维码刷新.

    :return: 如果成功登录返回 True, 其他情况返回 False.
    """
    login_url = "https://seat-lib.ecnu.edu.cn"
    WebDriverWait(driver, timeout).until(
        EC.any_of(
            attribute_changes(QRCODE_IMG, "src"),
            EC.url_matches(login_url),
        )
    )
    return login_url in driver.current_url


def _get_qrcode(driver: Edge, timeout: float) -> tuple[str, str]:
    """
    获取统一登陆界面中的登录二维码.

    :return: (登录二维码扫描出来的网址(如果扫描失败则为二维码网址), 登录二维码 base64 数据(其可直接放入 img 元素的 src 字段))
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, QRCODE_IMG))
    )
    img_base64_data = driver.execute_script(EXTRACT_QRCODE_JS)
    img_base64 = base64.b64decode(img_base64_data.split(",")[1])
    img = Image.open(io.BytesIO(img_base64))
    decoded = pyzbar.decode(img)
    try:
        url = decoded[0].data.decode("utf-8")
    except Exception:
        logger.error("failed to decode qrcode.")
        url = driver.execute_script(EXTRACT_QRCODE_SRC_JS)
    logger.debug("qrcode base64 data: "
                 + img_base64_data[:min(30, len(img_base64_data))] + "...")
    logger.debug("qrcode url: " + url)
    return url, img_base64_data


def _get_temp_qrcode_file(img_base64_data: str) -> str:
    """
    根据 base64 (Data URI Scheme) 创建临时图片文件, 返回临时文件的路径.
    """
    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".png", delete=False) as f:
        f.write(base64.b64decode(img_base64_data.split(",")[1]))
    return f.name


def get_default_grabbers():
    return [LibCache.grab_from_driver, PortalCache.grab_from_driver]


@requires_init
def get_login_cache(
        cache_grabbers: Sequence[Callable[[Edge], Any]] = tuple(get_default_grabbers()),
        timeout: float = 24 * 60,
        qrcode_callback: Callable[[str, str, bool], None] = lambda s1, s2, b1: None,
) -> Optional[LoginCache]:
    """
    使用浏览器的进行图书馆的登录操作,
    并获取相应的登录缓存, 以供爬虫部分使用.

    如果登录失败或者超时, 返回 None.

    todo 暂时只支持了图书馆内登录缓存的获取, 其他 ecnu 功能正在开发.

    Parameters:
        cache_grabbers: 一系列函数, 用于从 seleniumwire 的 EdgeDriver 中获取 Cache 对象.
            这些函数满足: 第一个参数, 是 Edge 的 WebDriver 对象, 返回值为元组 (Cache 名称, Cache 对象).
            可以使用 get_default_grabbers() + [...] 的方式填充参数.
        timeout: 在某个操作等待时间超过 timeout 时, 停止等待, 终止登录逻辑.
        qrcode_callback: 一个函数, 用于回调提醒用户登录.
            - 参数 1 为 ECNU uia 登录二维码的临时文件路径, 该文件保存在 %TEMP% 目录下, 脚本不对其进行清理操作.
            - 参数 2 为二维码解析结果, 如果脚本解析二维码失败则此参数是二维码网址.
            - 参数 3 为是否是因为二维码超时而刷新产生的回调.

    Returns:
        如果登陆成功, 返回登录缓存; 如果登录失败或超时, 返回 None.
    """
    driver = Edge()
    try:
        driver.maximize_window()
        driver.get("https://seat-lib.ecnu.edu.cn/h5/#/SeatScreening/1")
        # 此时重定向至 ecnu 统一认证界面, 用户登录后返回至 seat-lib.ecnu.edu.cn 域名下.

        # 获取 ecnu 统一认证界面的登录二维码并通过邮箱或微信发送给用户.
        click_element(driver, QRCODE_BUTTON, timeout)  # 确保二维码显示出来.
        url, img_base64_data = _get_qrcode(driver, timeout)
        file = _get_temp_qrcode_file(img_base64_data)
        qrcode_callback(file, url, False)

        logger.info("uia waiting for login.")
        while not _wait_qrcode_update_or_login(driver, timeout):  # 等待用户成功登录或者二维码超时.
            # 二维码超时刷新.
            driver.maximize_window()  # 最大化窗口, 增加成功捕获二维码的可能性.
            logger.info("uia login qrcode updated.")
            url, img_base64_data = _get_qrcode(driver, timeout)
            file = _get_temp_qrcode_file(img_base64_data)
            qrcode_callback(file, url, False)

        # 提取 cache.
        login_cache = LoginCache()
        for cache_grabber in cache_grabbers:
            try:
                cache = cache_grabber(driver)
                login_cache.add_cache(cache)
            except Exception as e:
                logger.error(f"Exception during grabbing cache: {type(e)}, {e}")
        logger.debug(f"login cache: {login_cache}")
        return login_cache
    except TimeoutException:
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
    return None
