#!/usr/bin/env python3
"""
fetch_energy.py — 能源 / 电网 / 气象外生冲击（P1 归并模块）

归并能源相关源（符合"电网 + 气象归一个 fetch_energy.py"的改造要求）：
  - 英国 Carbon Intensity API（NESO 运营，免key）：电网碳强度 + 发电结构
        -> 主信号 grid_carbon_risk（GRV 直接消费 energy_grid_risk 维度）
  - National Grid ESO (NESO) BMRS：需免费 API key；未配则降级（不强行 401 调用，避免日志噪声）
  - NREL PVWatts（太阳能发电估算，apiKey）：可选，落盘
  - AEMet（西班牙气象局，apiKey）：可选，落盘（端点未在本环境核实，调用失败安全降级）

各子源独立 status，互不影响；任一下游失败不阻断整体。

输出契约：data/energy_risk.json
  {
    "status":             "ok" | "partial" | "unavailable",
    "grid_carbon_risk":   0–100,   # 主信号，喂 GRV energy_grid_risk（高=脏电网/化石占比高）
    "uk_grid":            {status, intensity_forecast, intensity_index, generation_mix, fossil_share_pct, grid_carbon_risk},
    "national_grid_eso":  {status, ...},
    "pvwatts":            {status, solrad_annual_kwh_m2, ac_annual_kwh},
    "aemet":              {status, ...},
    "source":             "UK Carbon Intensity / NESO / NREL / AEMet",
    "updated":            as-of
  }
  geo_risk_vector.py 直接读 grid_carbon_risk 填 grv_latest.json 的 energy_grid_risk。

降级：每子源独立 try/except；整体不可用时若本地有上次良值则保留、不覆盖、绝不 crash。

网络出口：直连优先，失败回退代理，仍失败降级（各源出口实测见交付报告）。
调度：scheduler.py 06:08（grv_update 06:10 前完成）。
"""
import os
import json

try:
    from optim_config import (
        DATA_DIR, PROXY_URL,
        UK_CARBON_INTENSITY_BASE,
        NATIONAL_GRID_ESO_BMRS_KEY,
        NREL_API_KEY, NREL_PVWATTS_URL,
        AEMET_API_KEY, AEMET_BASE,
    )
except ImportError:
    _cfg = FetcherBase.load_config_with_fallback(
        ["DATA_DIR", "PROXY_URL", "UK_CARBON_INTENSITY_BASE",
         "NATIONAL_GRID_ESO_BMRS_KEY", "NREL_API_KEY", "NREL_PVWATTS_URL",
         "AEMET_API_KEY", "AEMET_BASE"],
        {
            "DATA_DIR": FetcherBase.default_data_dir(),
            "PROXY_URL": ("", "PROXY_URL"),
            "UK_CARBON_INTENSITY_BASE": ("https://api.carbonintensity.org.uk", "UK_CARBON_INTENSITY_BASE"),
            "NATIONAL_GRID_ESO_BMRS_KEY": ("", "NATIONAL_GRID_ESO_BMRS_KEY"),
            "NREL_API_KEY": ("", "NREL_API_KEY"),
            "NREL_PVWATTS_URL": ("https://developer.nrel.gov/api/pvwatts/v8.json", "NREL_PVWATTS_URL"),
            "AEMET_API_KEY": ("", "AEMET_API_KEY"),
            "AEMET_BASE": ("https://opendata.aemet.es/opendata/api", "AEMET_BASE"),
        },
    )
    DATA_DIR = _cfg["DATA_DIR"]
    PROXY_URL = _cfg["PROXY_URL"]
    UK_CARBON_INTENSITY_BASE = _cfg["UK_CARBON_INTENSITY_BASE"]
    NATIONAL_GRID_ESO_BMRS_KEY = _cfg["NATIONAL_GRID_ESO_BMRS_KEY"]
    NREL_API_KEY = _cfg["NREL_API_KEY"]
    NREL_PVWATTS_URL = _cfg["NREL_PVWATTS_URL"]
    AEMET_API_KEY = _cfg["AEMET_API_KEY"]
    AEMET_BASE = _cfg["AEMET_BASE"]

from fetcher_base import FetcherBase

OUTPUT_FILE = "energy_risk.json"
# 碳强度映射边界（gCO2/kWh）：典型 20(绿)–320(脏)；经验边界 30/320
_CI_LOW = 30.0
_CI_HIGH = 320.0
# 化石燃料种类（用于发电结构化石占比）
_FOSSIL_FUELS = ("gas", "coal", "oil")


class EnergyFetcher(FetcherBase):
    name = "energy"
    rate_interval = 1.0
    output_file = OUTPUT_FILE
    feeds_grv = True
    schedule = "0608"

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.proxies = None

    # ── 网络出口：直连优先，失败回退代理 ────────────────────────
    def _get(self, url, params=None, headers=None, timeout=20):
        r = self.request(url, params=params, headers=headers, timeout=timeout)
        if r is not None:
            return r
        if PROXY_URL:
            self.proxies = {"http": PROXY_URL, "https": PROXY_URL}
            return self.request(url, params=params, headers=headers, timeout=timeout)
        return None

    # ── UK Carbon Intensity（免key，主信号源）──────────────────
    def _fetch_uk_grid(self) -> dict:
        out = {"status": "unavailable", "reason": "unknown"}
        intensity_url = f"{UK_CARBON_INTENSITY_BASE}/intensity"
        r = self._get(intensity_url)
        if r is None:
            out["reason"] = "intensity_unreachable"
            return out
        try:
            data = r.json().get("data", [{}])
            cur = data[0] if data else {}
            intensity = cur.get("intensity", {})
            forecast = intensity.get("forecast")
            actual = intensity.get("actual")
            index = intensity.get("index")

            # 发电结构（同 API 的 /generation 端点，免key）
            genmix = []
            rg = self._get(f"{UK_CARBON_INTENSITY_BASE}/generation")
            if rg is not None:
                try:
                    gdata = rg.json().get("data", [{}])
                    genmix = gdata[0].get("generationmix", []) if gdata else []
                except Exception:
                    genmix = []
            fossil = sum(float(g.get("perc", 0)) for g in genmix
                         if g.get("fuel") in _FOSSIL_FUELS)

            risk = None
            if isinstance(forecast, (int, float)):
                risk = round(min(100.0, max(0.0,
                              (forecast - _CI_LOW) / (_CI_HIGH - _CI_LOW) * 100)), 1)
            return {
                "status": "ok",
                "intensity_forecast": forecast,
                "intensity_actual": actual,
                "intensity_index": index,
                "generation_mix": genmix,
                "fossil_share_pct": round(fossil, 1),
                "grid_carbon_risk": risk,
            }
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    # ── National Grid ESO BMRS（需免费 key；未配 / 端点未核实 → 降级）──
    def _fetch_national_grid_eso(self) -> dict:
        if not NATIONAL_GRID_ESO_BMRS_KEY:
            return {"status": "skipped", "reason": "no_bmrs_key",
                    "note": "National Grid ESO BMRS v2 需免费 API key；"
                            "UK 电网信号已由 Carbon Intensity API 覆盖"}
        # BMRS 具体端点需在部署时按 key 权限确认；此处不强行调用，避免 401 噪声。
        return {"status": "skipped", "reason": "unverified_endpoint",
                "note": "BMRS 端点待部署时确认（未配 key 时已跳过）"}

    # ── NREL PVWatts（太阳能发电估算，apiKey）──────────────────
    def _fetch_pvwatts(self) -> dict:
        if not NREL_API_KEY:
            return {"status": "key_missing", "reason": "no_nrel_key"}
        params = {
            "api_key": NREL_API_KEY, "lat": 51.5, "lon": -0.12,
            "system_capacity": 4, "azimuth": 180, "tilt": 35,
            "array_type": 1, "module_type": 1, "losses": 10,
        }
        r = self._get(NREL_PVWATTS_URL, params=params)
        if r is None:
            return {"status": "unavailable", "reason": "unreachable"}
        try:
            outputs = r.json().get("outputs", {})
            return {"status": "ok",
                    "solrad_annual_kwh_m2": outputs.get("solrad_annual"),
                    "ac_annual_kwh": outputs.get("ac_annual")}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    # ── AEMet（西班牙气象局，apiKey；端点未完全核实）───────────
    def _fetch_aemet(self) -> dict:
        if not AEMET_API_KEY:
            return {"status": "key_missing", "reason": "no_aemet_key"}
        try:
            meta_url = f"{AEMET_BASE}/valores/climatologicos/ultimosdatosestacion/3195"
            r = self._get(meta_url, params={"api_key": AEMET_API_KEY})
            if r is None:
                return {"status": "unavailable", "reason": "unreachable"}
            d = r.json()
            datos = d.get("datos")
            if not datos:
                return {"status": "unavailable", "reason": "no_datos_url"}
            rd = self._get(datos)
            if rd is None:
                return {"status": "unavailable", "reason": "datos_unreachable"}
            return {"status": "ok", "sample": rd.json()}
        except Exception as e:
            return {"status": "unavailable", "reason": f"parse_error:{e}"}

    def collect(self):
        uk = self._fetch_uk_grid()
        eso = self._fetch_national_grid_eso()
        pvw = self._fetch_pvwatts()
        aem = self._fetch_aemet()

        statuses = [s.get("status") for s in (uk, eso, pvw, aem)]
        if all(s in ("unavailable", "skipped", "key_missing") for s in statuses):
            overall = "unavailable"
        elif uk.get("status") == "ok":
            overall = "ok"
        else:
            overall = "partial"

        grid_risk = uk.get("grid_carbon_risk")
        return {
            "status": overall,
            "grid_carbon_risk": grid_risk,   # 主信号，喂 GRV energy_grid_risk
            "uk_grid": uk,
            "national_grid_eso": eso,
            "pvwatts": pvw,
            "aemet": aem,
            "source": "UK Carbon Intensity / NESO / NREL / AEMet",
        }

    def _is_good(self, data: dict) -> bool:
        # 主信号 grid_carbon_risk 非空才算良值
        return data.get("status") in ("ok", "partial") and data.get("grid_carbon_risk") is not None

def main():
    fetcher = EnergyFetcher(DATA_DIR)
    result = fetcher.run()
    if not result:
        print("[energy] collect 异常返回空，保留旧值（不覆盖）")
        return
    if result.get("status") in ("ok", "partial"):
        fetcher.save_json(OUTPUT_FILE, result)
        print(f"[energy] 完成 status={result.get('status')}，"
              f"grid_carbon_risk={result.get('grid_carbon_risk')}")
    else:
        prev = fetcher.load_previous_good()
        if prev is not None:
            print("[energy] 降级 unavailable，本地存在上次良值，保留不覆盖")
        else:
            fetcher.save_json(OUTPUT_FILE, result)
            print("[energy] 降级 unavailable，无历史良值，写 unavailable 标记")


if __name__ == "__main__":
    main()
