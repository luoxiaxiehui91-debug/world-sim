#!/usr/bin/env python3
"""
fetch_spacetrack.py — Space-Track.org 卫星统计
凭证：REDACTED_SPACETRACK_ID / 见 S:\KEY\Space-Track.txt

统计：
- 活跃在轨卫星总数（DECAY=null）
- 按类型：PAYLOAD / ROCKET BODY / DEBRIS / UNKNOWN
- Starlink 在轨数
- OneWeb 在轨数
- 近30天新发射对象数
- 军事卫星代理（US+RUS+CHN PAYLOAD，近期轨道）

输出：data/spacetrack.json
调度：scheduler.py 每日 06:15（日频，错峰）。feeds_grv=False。

API 限制：
- 每小时最多 30 次请求（免费账号）
- 每次 limit 建议不超过 1000
- 本 fetcher 每天只跑一次，发 5 个轻量统计请求，远低于限制
"""
import os
import json
import datetime
import logging
from datetime import timezone

import requests
from fetcher_base import FetcherBase, Status

_cfg = FetcherBase.load_config_with_fallback(
    ["DATA_DIR", "PROXY_URL"],
    {
        "DATA_DIR":  FetcherBase.default_data_dir(),
        "PROXY_URL": ("http://192.168.31.108:7890", "PROXY_URL"),
    },
)
DATA_DIR        = _cfg["DATA_DIR"]
PROXY_URL       = _cfg["PROXY_URL"]
# 凭证优先从环境变量读，其次用默认值（见 S:\KEY\Space-Track.txt）
SPACETRACK_ID   = os.environ.get("SPACETRACK_ID",   "REDACTED_SPACETRACK_ID")
SPACETRACK_PASS = os.environ.get("SPACETRACK_PASS",  "REDACTED_SPACETRACK_PASS")

BASE     = "https://www.space-track.org"
OUTPUT   = "spacetrack.json"


class SpaceTrackFetcher(FetcherBase):
    name          = "spacetrack"
    rate_interval = 2.0
    output_file   = OUTPUT
    feeds_grv     = False
    schedule      = "0615"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self._session = None

    def _get_session(self):
        if self._session:
            return self._session
        s = requests.Session()
        if PROXY_URL:
            s.proxies = {"https": PROXY_URL, "http": PROXY_URL}
        r = s.post(f"{BASE}/ajaxauth/login",
                   data={"identity": SPACETRACK_ID, "password": SPACETRACK_PASS},
                   timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Space-Track login failed: {r.status_code}")
        self._session = s
        return s

    def _query(self, path: str, limit: int = 10000) -> list | None:
        """轻量 count 查询，返回记录列表。"""
        s = self._get_session()
        url = f"{BASE}/basicspacedata/query/class/satcat/{path}/format/json/limit/{limit}"
        r = s.get(url, timeout=30)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return None
        self.logger.warning("[spacetrack] query failed %s %d", path, r.status_code)
        return None

    def _count(self, rows: list | None, **filters) -> int:
        """从结果集里按字段过滤并计数。"""
        if rows is None:
            return 0
        result = rows
        for k, v in filters.items():
            result = [r for r in result if r.get(k) == v]
        return len(result)

    def collect(self):
        try:
            s = self._get_session()
        except Exception as e:
            self.logger.error("[spacetrack] 登录失败: %s", e)
            return None

        now = datetime.datetime.now(timezone.utc)
        cutoff_30d = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%d")

        # 1. 全部活跃在轨对象（DECAY=null）
        all_active = self._query("DECAY/null-val/CURRENT/Y", limit=30000)
        total_active = len(all_active) if all_active else 0

        payload_count  = self._count(all_active, OBJECT_TYPE="PAYLOAD")
        debris_count   = self._count(all_active, OBJECT_TYPE="DEBRIS")
        rocket_count   = self._count(all_active, OBJECT_TYPE="ROCKET BODY")
        unknown_count  = self._count(all_active, OBJECT_TYPE="UNKNOWN")

        # 2. Starlink
        starlink_rows = self._query("SATNAME/STARLINK~~/DECAY/null-val/CURRENT/Y", limit=10000)
        starlink_count = len(starlink_rows) if starlink_rows else 0

        # 3. OneWeb
        oneweb_rows = self._query("SATNAME/ONEWEB~~/DECAY/null-val/CURRENT/Y", limit=5000)
        oneweb_count = len(oneweb_rows) if oneweb_rows else 0

        # 4. 近30天新发射对象数
        recent_rows = self._query(f"LAUNCH/>{cutoff_30d}/CURRENT/Y", limit=2000)
        new_objects_30d = len(recent_rows) if recent_rows else 0

        # 5. 军事卫星代理（US大型 PAYLOAD 非商业）
        # 用 RCS_SIZE=LARGE + COUNTRY=US/RUS/CHN，近似军事载荷
        military_proxy = 0
        if all_active:
            mil = [r for r in all_active
                   if r.get("OBJECT_TYPE") == "PAYLOAD"
                   and r.get("COUNTRY") in ("US", "RUS", "CHN")
                   and r.get("RCS_SIZE") == "LARGE"]
            military_proxy = len(mil)

        # 退出登录
        try:
            s.get(f"{BASE}/ajaxauth/logout", timeout=10)
            self._session = None
        except Exception:
            pass

        self.logger.info(
            "[spacetrack] active=%d payload=%d debris=%d starlink=%d new30d=%d",
            total_active, payload_count, debris_count, starlink_count, new_objects_30d
        )

        result = {
            "status":          Status.OK,
            "_schema_version": "1.0",
            "updated":         now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_active":    total_active,
            "by_type": {
                "payload":     payload_count,
                "debris":      debris_count,
                "rocket_body": rocket_count,
                "unknown":     unknown_count,
            },
            "constellations": {
                "starlink":    starlink_count,
                "oneweb":      oneweb_count,
            },
            "new_objects_30d": new_objects_30d,
            "military_large_payload": military_proxy,
            "source": "Space-Track.org SATCAT",
            "note": "military_large_payload 为 US/RUS/CHN 大型载荷近似计数，非精确军事分类",
        }

        # 直接写出文件（兼容 scheduler 直接调用）
        try:
            import json as _json
            out = os.path.join(DATA_DIR, OUTPUT)
            with open(out, "w", encoding="utf-8") as _f:
                _json.dump(result, _f, ensure_ascii=False, indent=2)
        except Exception as _we:
            self.logger.warning("[spacetrack] 写文件失败: %s", _we)

        return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    fetcher = SpaceTrackFetcher(DATA_DIR)
    data = fetcher.collect()
    if data:
        import json
        out = os.path.join(DATA_DIR, OUTPUT)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[spacetrack] 写入 {out}，active={data.get('total_active')}")
    else:
        print("[spacetrack] 采集失败，未写文件")
