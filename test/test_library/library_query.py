import os
import pickle
import unittest

from src.config import init, logger
from src.uia.login import get_login_cache, LibCache
from src.library.query import LibraryQuery

LOGIN_CACHE_FILE = "login-cache.pickle"


def load_cache():
    if os.path.exists(LOGIN_CACHE_FILE):
        with open(LOGIN_CACHE_FILE, "rb") as f:
            login_cache = pickle.load(f)
    else:
        login_cache = get_login_cache()
        with open(LOGIN_CACHE_FILE, "wb") as f:
            pickle.dump(login_cache, f)
    return login_cache


class LibraryQueryTest(unittest.TestCase):
    def setUp(self):
        init()
        self.cache = load_cache()
        self.q = LibraryQuery(self.cache.get_cache(LibCache))

    def test_quick_select(self):
        qs = self.q.quick_select()
        id_ = qs.get_most_free_seats_area()
        most_free_seats = qs.get_by_id(id_)
        logger.info(most_free_seats)
        storey = qs.get_by_id(int(most_free_seats["parentId"]))
        logger.info(storey)
        premises = qs.get_by_id(int(storey["parentId"]))
        logger.info(premises)
        logger.info(qs.get_premises_of(id_))
        logger.info(qs.get_premises_of(21))

    def test_query_date(self):
        qs = self.q.quick_select()
        id_ = qs.get_most_free_seats_area()
        days = self.q.query_date(id_)
        logger.info(days)

    def test_query_seats(self):
        qs = self.q.quick_select()
        id_ = qs.get_most_free_seats_area()
        days = self.q.query_date(id_)
        ret = self.q.query_seats(id_, days[0].times[0])
        logger.info(ret)
