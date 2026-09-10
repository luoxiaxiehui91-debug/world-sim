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
        "PROXY_URL": ("", "PROXY_URL"),
    },
)
DATA_DIR        = _cfg["DATA_DIR"]
PROXY_URL       = _cfg["PROXY_URL"]
# 凭证从环境变量读（SPACETRACK_ID / SPACETRACK_PASS），见 S:\KEY\Space-Track KEY.txt
SPACETRACK_ID   = os.environ.get("SPACETRACK_ID")
SPACETRACK_PASS = os.environ.get("SPACETRACK_PASS")

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
        # 2026-09-08: Space-Track 对错误凭证返回 HTTP 200 + {"Login":"Failed"}，
        # 仅校验状态码会把登录失败当成功，错误推迟到下游查询才以 401 暴露
        # （曾致开阳宇宙监视静默清零 10 天 / 40 次 401 无告警）。此处校验响应体：
        # 登录成功时 body 为空串，若解析出含 Login 键的 JSON 一律视为被拒。
        _body = (r.text or "").strip()
        if _body:
            try:
                _j = json.loads(_body)
            except Exception:
                _j = None
            if isinstance(_j, dict) and any(str(k).lower() == "login" for k in _j):
                raise RuntimeError(
                    f"Space-Track login rejected (HTTP 200 but body says failed): {_body[:200]}")
        self._session = s
        return s

    def _query(self, path: str, limit: int = 10000, timeout: int = 30) -> list | None:
        """轻量 count 查询，返回记录列表。大结果集需调大 timeout（默认 30s 不够）。"""
        s = self._get_session()
        url = f"{BASE}/basicspacedata/query/class/satcat/{path}/format/json/limit/{limit}"
        r = s.get(url, timeout=timeout)
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
        # 2026-09-08: 原 limit=30000 恰等于返回值（截断），真实为 35048；
        # 提至 100000 并放宽 timeout（大结果集约需 60-90s）
        all_active = self._query("DECAY/null-val/CURRENT/Y", limit=100000, timeout=120)
        total_active = len(all_active) if all_active else 0

        payload_count  = self._count(all_active, OBJECT_TYPE="PAYLOAD")
        debris_count   = self._count(all_active, OBJECT_TYPE="DEBRIS")
        rocket_count   = self._count(all_active, OBJECT_TYPE="ROCKET BODY")
        unknown_count  = self._count(all_active, OBJECT_TYPE="UNKNOWN")

        # 2. Starlink
        # 原 limit=10000 恰等于返回值（截断），真实为 11083
        starlink_rows = self._query("SATNAME/STARLINK~~/DECAY/null-val/CURRENT/Y", limit=30000)
        starlink_count = len(starlink_rows) if starlink_rows else 0

        # 3. OneWeb
        # 统一口径（当前 654 未触顶，无影响）
        oneweb_rows = self._query("SATNAME/ONEWEB~~/DECAY/null-val/CURRENT/Y", limit=30000)
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

        # 2026-09-08: 按查询结果判定状态，禁止把失败粉饰为 ok
        # （曾掩盖凭证错误 10 天：查询全 401 仍写 status=ok + 全 0）
        _sub_results = {
            "starlink": starlink_rows,
            "oneweb":   oneweb_rows,
            "recent":   recent_rows,
        }
        if all_active is None:
            _feed_status = Status.UNAVAILABLE
            _err = "核心查询 DECAY/null-val/CURRENT/Y 失败"
        else:
            _bad = [k for k, v in _sub_results.items() if v is None]
            if _bad:
                _feed_status = Status.PARTIAL
                _err = "子查询失败: " + ",".join(_bad)
            else:
                _feed_status = Status.OK
                _err = None
        if _feed_status != Status.OK:
            self.logger.error("[spacetrack] 采集 %s: %s", _feed_status, _err)

        result = {
            "status":          _feed_status,
            "error":           _err,
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

        # 非 OK 时保留上次成功值，避免面板显示 0 造成"清零"式误导
        if _feed_status != Status.OK:
            try:
                with open(os.path.join(DATA_DIR, OUTPUT), encoding="utf-8") as _pf:
                    _prev = json.load(_pf)
                if isinstance(_prev, dict) and _prev.get("status") == Status.OK:
                    for _k in ("total_active", "by_type", "constellations",
                               "new_objects_30d", "military_large_payload"):
                        if _k in _prev:
                            result[_k] = _prev[_k]
                    self.logger.warning("[spacetrack] 沿用上次成功值（本次 %s）", _feed_status)
            except Exception:
                pass

        # 直接写出文件（兼容 scheduler 直接调用）
        try:
            import json as _json
            out = os.path.join(DATA_DIR, OUTPUT)
            _tmp_173 = out + ".tmp"
            with open(_tmp_173, "w", encoding="utf-8") as _f:
                _json.dump(result, _f, ensure_ascii=False, indent=2)
            os.replace(_tmp_173, out)
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
