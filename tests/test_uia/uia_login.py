import unittest

from src.log import init, project_logger
from src.email import EmailSender
from src.portal import PortalCache
from src.uia.login import get_login_cache, FIRST_QRCODE_TITLE, UPDATED_QRCODE_TITLE, QRCODE_HTML
from src.wechat import wx


class LoginTest(unittest.TestCase):
    """填入邮箱相关信息后才能运行第一个测试"""
    def setUp(self):
        init()

    def test_login(self):
        project_logger.info(get_login_cache(cache_grabbers=[PortalCache.grab_from_driver]))

    def test_email_notice_login(self):
        sender = EmailSender(sender="", password="", receiver="", smtp_host=("smtp.qq.com", 465))
        sender.connect()

        def cb(file: str, url: str, retry: bool):
            title = FIRST_QRCODE_TITLE if not retry else UPDATED_QRCODE_TITLE
            sender.send_html_with_attachments(
                title,
                QRCODE_HTML.format(
                    title=title,
                    img="cid:qrcode",
                    url=url,
                ),
                [(file, "qrcode")]
            )

        login_cache = get_login_cache(qrcode_callback=cb)
        if login_cache:
            sender.send_text_email("Login Successfully", "Login to ECNU successfully.")
        else:
            self.fail()

    def test_wechat_notice_login(self):
        chat = "文件传输助手"

        def cb(file, url, _):
            wx.send_message(chat, "请点击链接或者扫描二维码登录 ECNU 统一认证")
            wx.send_message(chat, url)
            wx.send_img(chat, file)

        login_cache = get_login_cache(timeout=60, qrcode_callback=cb)
        if login_cache:
            wx.send_message(chat, "登录成功")
        else:
            wx.send_message(chat, "登录错误")
            self.fail()
