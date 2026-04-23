"""CVE watcher — query NIST NVD 2.0 for vulns affecting the router.

Uses the public CVE search (keyword) as a free alternative to the CPE match API,
which needs a registered key for reasonable rate limits. Hits are matched against
installed firmware version by substring.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import requests

from . import db as db_mod

log = logging.getLogger(__name__)
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def fetch_cves(keyword: str, results_per_page: int = 50) -> list[dict]:
    params = {"keywordSearch": keyword, "resultsPerPage": results_per_page}
    url = f"{NVD_URL}?{urlencode(params)}"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "c6u-cve-watcher/1.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("NVD fetch failed: %s", e)
        return []
    out = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id")
        descs = cve.get("descriptions", []) or []
        desc = next((d["value"] for d in descs if d.get("lang") == "en"), "")
        metrics = cve.get("metrics", {}) or {}
        cvss = None
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            m = metrics.get(key)
            if m:
                cvss = (m[0].get("cvssData") or {}).get("baseScore")
                break
        out.append({
            "id": cve_id, "description": desc, "cvss": cvss,
            "published": cve.get("published"),
            "last_modified": cve.get("lastModified"),
        })
    return out


def check(model: str, firmware: str | None = None) -> dict:
    model_clean = (model or "").lower().replace(" ", "_")
    candidates: list[str] = []
    # Make a best guess at the keyword — "tp-link archer c6u".
    if "tp-link" not in model_clean and "tplink" not in model_clean:
        candidates.append(f"tp-link {model}")
    else:
        candidates.append(model)
    cves: list[dict] = []
    seen: set[str] = set()
    for kw in candidates:
        for c in fetch_cves(kw):
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            cves.append(c)
    matching_fw: list[dict] = []
    if firmware:
        fw_short = firmware.split()[0] if firmware else ""
        for c in cves:
            if fw_short and fw_short.lower() in c["description"].lower():
                matching_fw.append(c)
    result = {
        "model": model, "firmware": firmware,
        "total": len(cves), "matching_firmware": len(matching_fw),
        "cves": cves, "firmware_hits": matching_fw,
        "ts": int(time.time()),
    }
    db_mod.record_event("cve_check",
        payload=f"total={len(cves)} match_fw={len(matching_fw)}")
    return result
