#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""Gamestats Database module.

    GamestatsHTTP Server Project
    Copyright (C) 2017  Sepalani

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sqlite3

from contextlib import closing
from datetime import datetime, timedelta

DATABASE_PATH = "gamestats2.db"
DATABASE_TIMEOUT = 5.0


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def init(path=DATABASE_PATH):
    """Initialize Gamestats database."""
    conn = sqlite3.connect(path, timeout=DATABASE_TIMEOUT)
    c = conn.cursor()

    # Gamestats
    c.execute("CREATE TABLE IF NOT EXISTS storage"
              " (gamename TEXT, pid INT, region TEXT, data TEXT,"
              " updated DATETIME)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_storage"
              " ON storage (gamename, pid, region)")

    # Gamestats2
    c.execute("CREATE TABLE IF NOT EXISTS ranking"
              " (gamename TEXT, pid INT, region INT, category INT,"
              " score INT, data TEXT, updated DATETIME)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_ranking"
              " ON ranking (gamename, pid, region, category)")

    conn.commit()
    conn.close()


def get2_dictrow(gamename, pid, region, category,
                 score=0, data=b"", updated=0):
    return {
        "gamename": gamename,
        "pid": pid,
        "region": region,
        "category": category,
        "score": score,
        "data": data,
        "updated": updated
    }


def sort_rows(data, rows, mine=None):
    """Sort rows."""
    if mine is None:
        # Rows already sorted
        return rows
    if data.get("filter", 1):
        rows.sort(key=lambda r: r["score"], reverse=True)
    else:
        rows.sort(key=lambda r: r["score"], reverse=False)
    return [mine] + rows


class GamestatsDatabase(object):
    """Gamestats database class."""
    FILTERS = {
        0: "ASC",
        1: "DESC"
    }

    def __init__(self, path=DATABASE_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path, timeout=DATABASE_TIMEOUT)
        self.conn.row_factory = dict_factory
        self.conn.text_factory = bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.conn.close()

    def root_download(self, gamename, pid, region):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM storage"
                " WHERE gamename = ? AND pid = ? AND region = ?",
                (gamename, pid, region)
            )
            return cursor.fetchone()

    def root_upload(self, gamename, pid, region, data):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO storage VALUES (?,?,?,?,?)",
                (gamename, pid, region, data, datetime.now())
            )
        self.conn.commit()

    def web_put2(self, gamename, pid, region, category, score, data):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO ranking VALUES (?,?,?,?,?,?,?)",
                (gamename, pid, region, category, score, data, datetime.now())
            )
        self.conn.commit()

    def web_get2_own(self, gamename, pid, region, category, data):
        with closing(self.conn.cursor()) as cursor:
            limit = ''
            parameters = (gamename, region, category, data["since"])
            if data.get("limit", 0):
                limit = " LIMIT ?"
                parameters = parameters + (data["limit"],)
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND updated >= ? ORDER BY score {}".format(
                    self.FILTERS.get(data.get("filter"), "")
                ) + limit, parameters
            )
            rows = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND updated >= ?",
                (gamename, region, category, data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, rows)

    def web_get2_top(self, gamename, pid, region, category, data):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND updated >= ? ORDER BY score {} LIMIT ?".format(
                    self.FILTERS.get(data.get("filter"), "")
                ),
                (gamename, region, category,
                 data["since"], data.get("limit", 10))
            )
            rows = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND updated >= ?",
                (gamename, region, category, data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, rows)

    def web_get2_nearby(self, gamename, pid, region, category, data):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid = ?",
                (gamename, region, category, pid)
            )
            mine = cursor.fetchone()
            if not mine:
                mine = get2_dictrow(gamename, pid, 0xFFFFFFFF, category)
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND updated >= ?"
                " ORDER BY ABS(? - score) {} LIMIT ?".format(
                    self.FILTERS.get(data.get("filter"), "")
                ),
                (gamename, region, category, pid, data["since"],
                 mine["score"], data.get("limit", 10) - 1)
            )
            others = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND updated >= ?",
                (gamename, region, category, pid, data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, others, mine)

    def web_get2_friends(self, gamename, pid, region, category, data):
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid = ?",
                (gamename, region, category, pid)
            )
            mine = cursor.fetchone()
            if not mine:
                mine = get2_dictrow(gamename, pid, 0xFFFFFFFF, category)
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region = ? AND category = ?"
                " AND pid IN ({}) AND updated >= ?"
                " ORDER BY score {} LIMIT ?".format(
                    ", ".join("{}".format(i) for i in data.get("friends", [])),
                    self.FILTERS.get(data.get("filter"), "")
                ),
                (gamename, region, category,
                 data["since"], data.get("limit", 10) - 1)
            )
            friends = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region = ? AND category = ?"
                " AND pid IN ({}) AND updated >= ?".format(
                    ", ".join("{}".format(i) for i in data.get("friends", [])),
                ),
                (gamename, region, category, data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, friends, mine)

    def web_get2_nearhi(self, gamename, pid, region, category, data):
        # TODO - Nearby high?
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid = ?",
                (gamename, region, category, pid)
            )
            mine = cursor.fetchone()
            if not mine:
                mine = get2_dictrow(gamename, pid, 0xFFFFFFFF, category)
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND (score - ?) >= 0 AND updated >= ?"
                " ORDER BY score {} LIMIT ?".format(
                    self.FILTERS.get(data.get("filter"), "")
                ),
                (gamename, region, category, pid, mine["score"],
                 data["since"], data.get("limit", 10) - 1)
            )
            others = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND (score - ?) >= 0 AND updated >= ?",
                (gamename, region, category, pid, mine["score"],
                 data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, others, mine)

    def web_get2_nearlo(self, gamename, pid, region, category, data):
        # TODO - Nearby low?
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid = ?",
                (gamename, region, category, pid)
            )
            mine = cursor.fetchone()
            if not mine:
                mine = get2_dictrow(gamename, pid, 0xFFFFFFFF, category)
            cursor.execute(
                "SELECT * FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND (score - ?) <= 0 AND updated >= ?"
                " ORDER BY score {} LIMIT ?".format(
                    self.FILTERS.get(data.get("filter"), "")
                ),
                (gamename, region, category, pid, mine["score"],
                 data["since"], data.get("limit", 10) - 1)
            )
            others = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total FROM ranking"
                " WHERE gamename = ? AND region & ? AND category = ?"
                " AND pid != ? AND (score - ?) <= 0 AND updated >= ?",
                (gamename, region, category, pid, mine["score"],
                 data["since"])
            )
            total = cursor.fetchone()["total"]
            return total, sort_rows(data, others, mine)

    def web_get2(self, gamename, pid, region, category, mode, data):
        # Time filter
        if data.get("updated", 0):
            data["since"] = datetime.now() - timedelta(minutes=data["updated"])
        else:
            data["since"] = datetime(1970, 1, 1)

        # Handle mode
        if mode == 0:
            return self.web_get2_own(gamename, pid, region, category, data)
        elif mode == 1:
            return self.web_get2_top(gamename, pid, region, category, data)
        elif mode == 2:
            return self.web_get2_nearby(gamename, pid, region, category, data)
        elif mode == 3:
            return self.web_get2_friends(gamename, pid, region, category, data)
        elif mode == 4:
            # Blind guess
            return self.web_get2_nearhi(gamename, pid, region, category, data)
        elif mode == 5:
            # Blind guess
            return self.web_get2_nearlo(gamename, pid, region, category, data)
        raise ValueError("Unknown get2 mode: {}".format(mode))


def root_download(gamename, pid, region, db_path=DATABASE_PATH):
    with GamestatsDatabase(db_path) as db:
        return db.root_download(gamename, pid, region)


def root_upload(gamename, pid, region, data, db_path=DATABASE_PATH):
    with GamestatsDatabase(db_path) as db:
        return db.root_upload(gamename, pid, region, data)


def web_put2(gamename, pid, region, category, score, data,
             db_path=DATABASE_PATH):
    with GamestatsDatabase(db_path) as db:
        return db.web_put2(gamename, pid, region, category, score, data)


def web_get2(gamename, pid, region, category, mode, data,
             db_path=DATABASE_PATH):
    with GamestatsDatabase(db_path) as db:
        return db.web_get2(gamename, pid, region, category, mode, data)


if __name__ == "__main__":
    pass
