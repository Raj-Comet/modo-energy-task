"""
ERCOT public data fetcher.

Downloads real historical market data from ERCOT's public MIS portal.
All endpoints used here are publicly available without authentication.

Usage
-----
    python -m src.ercot_fetcher --year 2024 --outdir data/

This module is optional — the app falls back to synthetic data if real
downloads fail or are not available locally.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

# ── ERCOT MIS base URLs ───────────────────────────────────────────────────────
# Settlement Point Prices (Day-Ahead)
DA_SPP_URL = (
    "https://www.ercot.com/misdownload/servlets/mirDownload"
    "?doclookupId={doc_id}"
)

# Publicly browsable report list endpoint used to discover doc IDs
REPORT_BROWSE_URL = (
    "https://www.ercot.com/misapp/servlets/IceDocListJsonWS"
    "?reportTypeId={report_type_id}&_={ts}"
)

# Report type IDs (from ERCOT MIS public documentation)
REPORT_TYPES = {
    "DA_SPP":        12301,   # Day-Ahead Settlement Point Prices
    "RT_SPP":        13061,   # Real-Time Settlement Point Prices  
    "AS_CLR":        12316,   # Ancillary Service Clearing Prices
}

SETTLEMENT_POINT = "HB_BUSAVG"   # Hub average — most representative


def _browse_reports(
    report_type_id: int, session: requests.Session, max_docs: int = 400
) -> list[dict]:
    """Return list of document metadata dicts from ERCOT MIS JSON feed."""
    url = REPORT_BROWSE_URL.format(
        report_type_id=report_type_id, ts=int(time.time() * 1000)
    )
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("ListDocsByRptTypeRes", {}).get("DocumentList", [])[:max_docs]
    except Exception as exc:
        log.warning("Failed to browse reports for type %s: %s", report_type_id, exc)
        return []


def _download_doc(doc_id: str, session: requests.Session) -> Optional[bytes]:
    try:
        r = session.get(
            DA_SPP_URL.format(doc_id=doc_id), timeout=30, stream=True
        )
        r.raise_for_status()
        return r.content
    except Exception as exc:
        log.warning("Failed to download doc %s: %s", doc_id, exc)
        return None


def _parse_da_spp_zip(content: bytes) -> pd.DataFrame:
    """Parse a DA SPP zip file → DataFrame with [timestamp, lmp]."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as f:
            df = pd.read_csv(f)

    # Normalise column names (ERCOT schema varies slightly across years)
    df.columns = [c.strip().upper() for c in df.columns]

    # Filter to hub average
    if "SETTLEMENTPOINT" in df.columns:
        df = df[df["SETTLEMENTPOINT"] == SETTLEMENT_POINT]
    elif "SETTLEMENT_POINT" in df.columns:
        df = df[df["SETTLEMENT_POINT"] == SETTLEMENT_POINT]

    # Parse timestamp
    ts_col = next(c for c in df.columns if "HOUR" in c or "DELIVERYHOUR" in c)
    date_col = next(c for c in df.columns if "DATE" in c and "HOUR" not in c)
    df["timestamp"] = pd.to_datetime(
        df[date_col].astype(str) + " " + (df[ts_col].astype(int) - 1).astype(str) + ":00"
    )

    price_col = next(c for c in df.columns if "PRICE" in c or "SPP" in c)
    return df[["timestamp", price_col]].rename(columns={price_col: "lmp"})


def fetch_year(
    year: int = 2024,
    outdir: str = "data/real",
    report_type: str = "DA_SPP",
) -> Optional[pd.DataFrame]:
    """
    Attempt to download a full year of ERCOT day-ahead SPPs.

    Returns a DataFrame or None if the download fails.
    """
    out_path = Path(outdir) / f"ercot_{report_type.lower()}_{year}.parquet"
    if out_path.exists():
        log.info("Cached file found: %s", out_path)
        return pd.read_parquet(out_path)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (ERCOT research; contact: research@example.com)"
    )

    log.info("Browsing ERCOT MIS for %s docs…", report_type)
    docs = _browse_reports(REPORT_TYPES[report_type], session)
    year_docs = [
        d for d in docs
        if str(year) in d.get("Document", {}).get("FriendlyName", "")
    ]
    log.info("Found %d documents for %s %s", len(year_docs), report_type, year)

    frames = []
    for doc_meta in year_docs:
        doc_id = doc_meta["Document"]["DocID"]
        content = _download_doc(doc_id, session)
        if content is None:
            continue
        try:
            df = _parse_da_spp_zip(content)
            frames.append(df)
        except Exception as exc:
            log.warning("Parse error for doc %s: %s", doc_id, exc)
        time.sleep(0.2)   # polite rate-limiting

    if not frames:
        log.error("No data retrieved — falling back to synthetic data")
        return None

    result = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    log.info("Saved %d rows → %s", len(result), out_path)
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Fetch ERCOT market data")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--outdir", default="data/real")
    parser.add_argument(
        "--report",
        choices=list(REPORT_TYPES.keys()),
        default="DA_SPP",
    )
    args = parser.parse_args()

    df = fetch_year(args.year, args.outdir, args.report)
    if df is not None:
        print(df.head())
        print(f"Shape: {df.shape}")
    else:
        print("Download failed — use synthetic data instead.")
