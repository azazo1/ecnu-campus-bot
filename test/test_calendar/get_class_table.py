import os
import pickle
import unittest
from pprint import pprint

from classtable.generate_latex_table import LatexGenerator
from src.config import init
from src.portal import PortalCache
from src.uia.login import get_login_cache
from src.portal.calendar.query import CalendarQuery

LOGIN_CACHE_FILE = "login-cache.pickle"


def load_cache():
    if os.path.exists(LOGIN_CACHE_FILE):
        with open(LOGIN_CACHE_FILE, "rb") as f:
            login_cache = pickle.load(f)
    else:
        login_cache = get_login_cache(cache_grabbers=[PortalCache.grab_from_driver])
        with open(LOGIN_CACHE_FILE, "wb") as f:
            pickle.dump(login_cache, f)
    return login_cache


class TestLatexGenerator(unittest.TestCase):
    def setUp(self):
        init()
        self.cache = load_cache()
        self.calendar = CalendarQuery(self.cache.get_cache(PortalCache))

    def test_class_table(self):
        class_table_dict = self.calendar.query_user_class_table()
        pprint(class_table_dict)

    def test_collector(self):
        class_table_dict = self.calendar.query_user_class_table()
        collected_info = CalendarQuery.collect_course_info(class_table_dict)
        pprint(collected_info)

    def test_generate_latex(self):
        class_table_dict = self.calendar.query_user_class_table()
        collected_info = CalendarQuery.collect_course_info(class_table_dict)
        generator = LatexGenerator(collected_info)
        generator.classify_courses()
        generator.generate_latex()
        generator.compile_latex()