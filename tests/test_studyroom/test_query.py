"""
    Tips: 本测试集仅用于测试接口是否正常工作, 不进行任何数据处理.
"""
import os
import pickle
import unittest
from pprint import pprint

from src.log import init, project_logger
from src.studyroom import StudyRoomCache
from src.studyroom.query import StudyRoomQuery
from src.uia.login import get_login_cache, LoginError

# 缓存文件路径
LOGIN_CACHE_FILE = "login-cache.pickle"


def load_cache() -> StudyRoomCache:
    """
    加载 StudyRoom 登录缓存。如果缓存文件不存在，则调用 grab_from_driver 获取新的缓存。
    """
    if os.path.exists(LOGIN_CACHE_FILE):
        with open(LOGIN_CACHE_FILE, "rb") as f:
            login_cache = pickle.load(f)
    else:
        # 如果缓存文件不存在，调用 `get_login_cache` 获取并保存
        login_cache = get_login_cache(cache_grabbers=[StudyRoomCache.grab_from_driver])
        with open(LOGIN_CACHE_FILE, "wb") as f:
            pickle.dump(login_cache, f)

    # 如果对应的缓存为空, 重新调用 grab_from_driver.
    if login_cache.get_cache(StudyRoomCache) is None:
        login_cache = get_login_cache(cache_grabbers=[StudyRoomCache.grab_from_driver])
        with open(LOGIN_CACHE_FILE, "wb") as f:
            pickle.dump(login_cache, f)

    return login_cache


class StudyRoomQueryTest(unittest.TestCase):
    """
        本测试集仅用于测试接口是否正常工作, 不进行任何数据处理.
    """

    def setUp(self):
        init()
        self.cache = load_cache()
        self.query = StudyRoomQuery(self.cache.get_cache(StudyRoomCache))

    def test_query_roomInfos(self):
        """
        测试查询校内所有研讨室的基础信息功能.

        URL: https://studyroom.ecnu.edu.cn/ic-web/roomDevice/roomInfos
        Method: GET

        Tips:
            该 Url 似乎会随着时间改变响应, 待后续考察.

            示例返回 :
            :   {'devId': 3676503,
                 'devName': '普陀校区单人间C421',
                 'minResvTime': 60,
                 'openTimes': [{'openEndTime': '22:00',
                                'openLimit': 1,
                                'openStartTime': '08:00'}],
                 'resvInfos': [{'resvBeginTime': '2024-12-26 '
                                                 '17:01:00',
                                'resvEndTime': '2024-12-26 '
                                               '21:01:00',
                                'resvStatus': 1093}]},
                {'devId': 3676511,
                 'devName': '普陀校区单人间C422',
                 'minResvTime': 60,
                 'openTimes': [{'openEndTime': '22:00',
                                'openLimit': 1,
                                'openStartTime': '08:00'}],
                 'resvInfos': [{'resvBeginTime': '2024-12-26 '
                                                 '18:00:00',
                                'resvEndTime': '2024-12-26 '
                                               '22:00:00',
                                'resvStatus': 1093}]},
        """
        rooms = self.query.query_roomInfos()
        pprint(rooms)

    def test_query_roomAvailable_today(self):
        """
        测试查询当前类别的研修间的预约情况的 Url 是否可用正常请求. [今天]

        URL: https://studyroom.ecnu.edu.cn/ic-web/roomDevice/roomAvailable
        Method: GET

        Tips:
            通过不同的 kindIds 参数来获取, kindId 从 query_room_infos 中获取.
        """
        rooms = self.query.query_roomsAvailable("today")
        for room in rooms:
            self.assertIn("devId", room, "房间信息缺少 devId")
            self.assertIn("devName", room, "房间信息缺少 devName")
        pprint(rooms)

    def test_query_roomAvailable_tomorrow(self):
        """
        测试查询当前类别的研修间的预约情况的 Url 是否可用正常请求. [明天]

        URL: https://studyroom.ecnu.edu.cn/ic-web/roomDevice/roomAvailable
        Method: GET

        Tips:
            通过不同的 kindIds 参数来获取, kindId 从 query_room_infos 中获取.
        """
        rooms = self.query.query_roomsAvailable("tomorrow")
        for room in rooms:
            self.assertIn("devId", room, "房间信息缺少 devId")
            self.assertIn("devName", room, "房间信息缺少 devName")
        pprint(rooms)

    def test_query_roomAvailable_day_after_tomorrow(self):
        """
        测试查询当前类别的研修间的预约情况的 Url 是否可用正常请求. [后天]

        URL: https://studyroom.ecnu.edu.cn/ic-web/roomDevice/roomAvailable
        Method: GET

        Tips:
            通过不同的 kindIds 参数来获取, kindId 从 query_room_infos 中获取.
        """
        rooms = self.query.query_roomsAvailable("day_after_tomorrow")
        for room in rooms:
            self.assertIn("devId", room, "房间信息缺少 devId")
            self.assertIn("devName", room, "房间信息缺少 devName")
        pprint(rooms)

    def test_invalid_cookie(self):
        """
        测试无效的 ic-cookie, 是否会抛出 LoginError.
        """
        invalid_cache = StudyRoomCache({"ic-cookie": "invalid_cookie"})
        invalid_query = StudyRoomQuery(invalid_cache)

        # 验证是否抛出 LoginError
        with self.assertRaises(LoginError) as context:
            invalid_query.query_roomInfos()

        self.assertIn("Result code: 300", str(context.exception))
        self.assertIn("用户未登录，请重新登录", str(context.exception))

    def test_query_resvInfo(self):
        """
        测试查询预约信息的 Url 是否可用正常请求.

        URL: https://studyroom.ecnu.edu.cn/ic-web/reserve/resvInfo
        Method: GET

        Tips:
            若没有预约任何研修间, 该测试点返回的数据为空.
        """
        resv_info = self.query.check_resvInfo(2) # 查询已预约未使用的研修间
        pprint(resv_info)