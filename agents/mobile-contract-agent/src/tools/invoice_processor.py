"""
invoice_processor.py
--------------------
Unified invoice extraction system that follows the smart routing architecture:

    PDF Upload → Layout Extractor → Fingerprint Engine
                                           |
                        +------------------+------------------+
                        |                                     |
                  Known Layout                          Unknown Layout
                        |                                     |
               Rule-based Extractor                  LLM Schema Generator
                        |                                     |
                        +------------------+------------------+
                                           |
                                   Structured Output

Flow:
  1. Extract word-level layout data from PDF pages
  2. Generate structural fingerprint
  3. Check if fingerprint matches known invoice format
  4. If KNOWN → Extract using existing rules (fast, no LLM)
  5. If UNKNOWN → Generate rules via LLM, save fingerprint, then extract
  6. Output structured data (CSV + JSON)

Usage:
    python invoice_processor2.py <pdf_folder> [vendor]

    # Process all PDFs in a folder (auto-detect vendor)
    python invoice_processor2.py /path/to/pdfs

    # Process all PDFs in a folder with a specific vendor
    python invoice_processor2.py /path/to/pdfs verizon
"""

import os
import json
import hashlib
import re
import logging
import sqlite3
import time
import contextlib
import gc
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter
import csv
import traceback
from urllib.parse import unquote, urlparse

import httpx
import pdfplumber
import pandas as pd
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import job status updater for database status tracking
try:
    from ..job_status_updater import update_job_status
except ImportError:
    # Graceful fallback when running as standalone CLI
    def update_job_status(*args, **kwargs):
        pass

# Optional json-repair library for LLM response repair
try:
    from json_repair import repair_json as _repair_json
    _JSON_REPAIR_AVAILABLE = True
except ImportError:
    _JSON_REPAIR_AVAILABLE = False
    _repair_json = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Silence the general azure-core and tables loggers
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.data.tables").setLevel(logging.WARNING)

# Silence verbose Databricks SQL connector logs (session open/close, HTTP 200s)
logging.getLogger("databricks.sql").setLevel(logging.WARNING)


# ═══════════════════════════════════════════════════════════════════════════
#                           CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

SQLITE_DB_PATH      = os.getenv("SQLITE_DB_PATH", "fingerprints.db")  # SQLite default

# RULES_DIR: filesystem path for vendor rule files.
# Dev        : "rules"       (default, relative to cwd)
# Production : "/mnt/rules"  (Azure Files mount — just set RULES_DIR env var,
#                              no code changes needed)
RULES_DIR  = Path(os.getenv("RULES_CACHE_DIR",  "/mnt/agentfiles/rules_cache"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "extracted_data"))

# Create directories if needed (no-op when path is an Azure Files mount)
try:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    # Log but don't crash - directories will be created on first use if needed
    pass

# ── Batch runner settings (edit here, no CLI flags needed) ────────────────
FORCE_GENERATE       = False   # True  → always call LLM (ignore fingerprint cache)
SIMILARITY_THRESHOLD = 0.9     # fingerprint match confidence (0.0–1.0)
VENDOR               = None    # e.g. "vivo" or "att", or None for auto-detect
MAX_PAGES            = 3000    # max pages to process per PDF (None = entire PDF)


# ═══════════════════════════════════════════════════════════════════════════
#                      1. LAYOUT EXTRACTOR (PDF → Words)
# ═══════════════════════════════════════════════════════════════════════════

def extract_words_from_page(page) -> List[Dict]:
    """
    Extract all words with positional data from a single pdfplumber page.
    
    Returns list of dicts: { text, x0, y0, x1, y1, font, size }
    """
    words = page.extract_words(
        x_tolerance=3,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=True,
        extra_attrs=["fontname", "size"],
    )
    clean = []
    for w in words:
        clean.append({
            "text": w.get("text", ""),
            "x0":   round(w.get("x0",     0), 2),
            "y0":   round(w.get("top",    0), 2),
            "x1":   round(w.get("x1",     0), 2),
            "y1":   round(w.get("bottom", 0), 2),
            "font": w.get("fontname", ""),
            "size": round(w.get("size",   0), 1),
        })
    return clean


def extract_layout_data(pdf_path: str, page_indices: List[int]) -> Dict:
    """
    Extract word-level layout data from specified PDF pages.
    
    Returns:
      {
        'pages': [{'page_num', 'width', 'height', 'words': [...]}],
        'all_words': [all words across pages with page_num tagged],
        'full_text': [plain text of each page],
        'tables': [extracted tables]
      }
    """
    result = {
        "pages": [],
        "all_words": [],
        "full_text": [],
        "tables": []
    }

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for idx in page_indices:
            if idx >= total:
                raise IndexError(
                    f"Page index {idx} (page {idx+1}) out of range (PDF has {total} pages)"
                )
            
            page = pdf.pages[idx]
            words = extract_words_from_page(page)
            
            # Tag each word with page number
            for w in words:
                w["page_num"] = idx + 1
            
            page_entry = {
                "page_num": idx + 1,
                "width":    round(float(page.width),  2),
                "height":   round(float(page.height), 2),
                "words":    words,
            }
            
            result["pages"].append(page_entry)
            result["all_words"].extend(words)
            result["full_text"].append(page.extract_text() or "")
            result["tables"].extend(page.extract_tables() or [])

            logger.info(
                f"Page {idx + 1}: extracted {len(words)} words "
                f"({page_entry['width']}×{page_entry['height']} pt)"
            )

    return result


# ═══════════════════════════════════════════════════════════════════════════
#                      2. FINGERPRINT ENGINE (Layout → ID)
# ═══════════════════════════════════════════════════════════════════════════

def cluster_coordinates(values: List[float], tolerance: float = 10.0) -> List[int]:
    """Cluster coordinate values to identify layout patterns."""
    if not values:
        return []
    
    sorted_vals = sorted(values)
    clusters = []
    current_cluster = [sorted_vals[0]]
    
    for val in sorted_vals[1:]:
        if val - current_cluster[-1] <= tolerance:
            current_cluster.append(val)
        else:
            clusters.append(len(current_cluster))
            current_cluster = [val]
    clusters.append(len(current_cluster))
    
    return clusters


def extract_layout_features(words: List[Dict], page_width: float, page_height: float) -> Dict:
    """Extract structural layout features that characterize invoice format."""
    if not words:
        return {}
    
    aspect_ratio = round(page_width / page_height, 2)
    
    # Coordinate clustering
    x_coords = [w["x0"] for w in words]
    x_clusters = cluster_coordinates(x_coords, tolerance=20)
    
    y_coords = [w["y0"] for w in words]
    y_clusters = cluster_coordinates(y_coords, tolerance=5)
    
    # Font patterns
    font_counts = Counter(w["font"] for w in words if w["font"])
    top_fonts = [font for font, _ in font_counts.most_common(3)]
    
    size_counts = Counter(w["size"] for w in words if w["size"])
    size_distribution = sorted([size for size, _ in size_counts.most_common(5)])
    
    # Regional density
    regions = {
        "top_left": 0, "top_right": 0,
        "mid_left": 0, "mid_right": 0,
        "bot_left": 0, "bot_right": 0,
    }
    
    mid_x = page_width / 2
    top_y = page_height / 3
    bot_y = 2 * page_height / 3
    
    for w in words:
        x, y = w["x0"], w["y0"]
        if y < top_y:
            prefix = "top"
        elif y < bot_y:
            prefix = "mid"
        else:
            prefix = "bot"
        suffix = "left" if x < mid_x else "right"
        regions[f"{prefix}_{suffix}"] += 1
    
    total_words = len(words)
    region_pct = {k: round(v / total_words * 100, 1) for k, v in regions.items()}
    
    return {
        "page_width": round(page_width, 1),
        "page_height": round(page_height, 1),
        "aspect_ratio": aspect_ratio,
        "word_count": total_words,
        "x_cluster_pattern": x_clusters[:10],
        "y_cluster_pattern": y_clusters[:10],
        "top_fonts": top_fonts,
        "size_distribution": size_distribution,
        "region_density": region_pct,
    }


# Module-level constant — built once, reused on every fingerprint call.
_SEMANTIC_ANCHOR_KEYWORDS: Dict[str, List[str]] = {
    "account": ["account", "customer", "client"],
    "invoice": ["invoice", "bill", "statement"],
    "date":    ["date", "issued"],
    "due":     ["due", "payment"],
    "total":   ["total", "amount", "balance"],
    "phone":   ["phone", "mobile", "wireless"],
    "usage":   ["usage", "summary", "consumption"],
    "plan":    ["plan", "service"],
    "data":    ["data", "internet"],
    "voice":   ["voice", "talk", "minutes"],
    "text":    ["text", "sms", "message"],
}
# Flat kw→anchor_name mapping (first declared wins) for single-pass extraction.
_KW_TO_ANCHOR: Dict[str, str] = {}
for _anchor_name, _kws in _SEMANTIC_ANCHOR_KEYWORDS.items():
    for _kw in _kws:
        _KW_TO_ANCHOR.setdefault(_kw, _anchor_name)
_ANCHOR_COUNT = len(_SEMANTIC_ANCHOR_KEYWORDS)


def extract_semantic_anchors(words: List[Dict]) -> Dict:
    """Find positions of common invoice keywords to create semantic fingerprint.

    Single-pass over the word list; stops as soon as all anchors are found.
    """
    anchors: Dict = {}
    for w in words:
        text_lower = w["text"].lower()
        for kw, anchor_name in _KW_TO_ANCHOR.items():
            if anchor_name not in anchors and kw in text_lower:
                anchors[anchor_name] = {
                    "x_pct": round(w["x0"] / 600 * 100, 1),
                    "y_pct": round(w["y0"] / 800 * 100, 1),
                }
        if len(anchors) == _ANCHOR_COUNT:
            break
    return anchors


# ── Vendor detection keywords — add a new entry here when onboarding a carrier ─
_VENDOR_DETECT_KEYWORDS: Dict[str, List[str]] = {
    "verizon": ["verizon"],
    "att":     ["at&t", "at&t", "att"],
    "vivo":    ["vivo"],
    "telekom": ["telekom", "t-mobile", "tmobile"],
}


def detect_vendor_hint(words: List[Dict]) -> Optional[str]:
    """Attempt to identify vendor from text content."""
    top_words = [w for w in words if w["y0"] < 150]
    for vendor, keywords in _VENDOR_DETECT_KEYWORDS.items():
        for w in top_words:
            if any(kw in w["text"].lower() for kw in keywords):
                return vendor

    return None


def generate_fingerprint(layout_data: Dict) -> Dict:
    """
    Generate structural fingerprint from layout data.
    
    Returns fingerprint dict with hash, layout_features, semantic_anchors, vendor_hint.
    Hash is derived from aspect ratio, cluster patterns, fonts, region density, and
    anchor positions — identical to fingerprint_generator.py for cross-tool compatibility.
    """
    all_words = layout_data["all_words"]
    if not all_words:
        raise ValueError("No words to fingerprint")
    
    first_page = layout_data["pages"][0]
    page_width = first_page["width"]
    page_height = first_page["height"]
    
    layout_features = extract_layout_features(all_words, page_width, page_height)
    semantic_anchors = extract_semantic_anchors(all_words)
    vendor_hint = detect_vendor_hint(all_words)
    
    # Generate stable hash — matches fingerprint_generator.py hash logic
    hash_input = {
        "aspect_ratio": layout_features.get("aspect_ratio"),
        "x_clusters": layout_features.get("x_cluster_pattern", []),
        "y_clusters": layout_features.get("y_cluster_pattern", []),
        "top_fonts": layout_features.get("top_fonts", []),
        "region_density": layout_features.get("region_density", {}),
        "anchors": semantic_anchors,
    }
    hash_str = json.dumps(hash_input, sort_keys=True)
    fingerprint_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:16]
    
    return {
        "hash": fingerprint_hash,
        "layout_features": layout_features,
        "semantic_anchors": semantic_anchors,
        "vendor_hint": vendor_hint,
    }


def calculate_similarity(fp1: Dict, fp2: Dict) -> float:
    """
    Calculate similarity score between two fingerprints (0.0 to 1.0).

    Weighted scoring across five dimensions:
      - Aspect ratio      10%  (continuous tolerance ±0.2)
      - Font overlap      15%
      - Region density    25%  (average % difference across 6 regions)
      - Anchor positions  40%  (spatial distance of shared keyword anchors)
      - Vendor hint       10%  (exact match bonus)
    """
    score = 0.0
    weights_sum = 0.0

    # 1. Aspect ratio similarity (weight: 10%)
    weight = 0.1
    ar1 = fp1.get("layout_features", {}).get("aspect_ratio", 0)
    ar2 = fp2.get("layout_features", {}).get("aspect_ratio", 0)
    if ar1 and ar2:
        ar_diff = abs(ar1 - ar2)
        score += weight * max(0, 1 - ar_diff * 5)  # Tolerates up to ±0.2 difference
        weights_sum += weight

    # 2. Font similarity (weight: 15%)
    weight = 0.15
    fonts1 = set(fp1.get("layout_features", {}).get("top_fonts", []))
    fonts2 = set(fp2.get("layout_features", {}).get("top_fonts", []))
    if fonts1 and fonts2:
        font_overlap = len(fonts1 & fonts2) / max(len(fonts1), len(fonts2))
        score += weight * font_overlap
        weights_sum += weight

    # 3. Region density similarity (weight: 25%)
    weight = 0.25
    regions1 = fp1.get("layout_features", {}).get("region_density", {})
    regions2 = fp2.get("layout_features", {}).get("region_density", {})
    if regions1 and regions2:
        region_keys = set(regions1.keys()) & set(regions2.keys())
        if region_keys:
            avg_diff = sum(abs(regions1[k] - regions2[k]) for k in region_keys) / len(region_keys)
            region_sim = max(0, 1 - avg_diff / 100)
            score += weight * region_sim
            weights_sum += weight

    # 4. Semantic anchor position similarity (weight: 40%)
    weight = 0.4
    anchors1 = fp1.get("semantic_anchors", {})
    anchors2 = fp2.get("semantic_anchors", {})
    if anchors1 and anchors2:
        common_anchors = set(anchors1.keys()) & set(anchors2.keys())
        if common_anchors:
            total_dist = 0
            for anchor in common_anchors:
                a1 = anchors1[anchor]
                a2 = anchors2[anchor]
                x_dist = abs(a1["x_pct"] - a2["x_pct"])
                y_dist = abs(a1["y_pct"] - a2["y_pct"])
                total_dist += (x_dist + y_dist) / 2
            avg_dist = total_dist / len(common_anchors)
            anchor_sim = max(0, 1 - avg_dist / 100)
            score += weight * anchor_sim
            weights_sum += weight

    # 5. Vendor hint exact match (weight: 10%)
    weight = 0.1
    vendor1 = fp1.get("vendor_hint")
    vendor2 = fp2.get("vendor_hint")
    if vendor1 and vendor2:
        if vendor1 == vendor2:
            score += weight
        weights_sum += weight

    # Normalize by actual weights used
    if weights_sum > 0:
        return score / weights_sum
    return 0.0


# ═══════════════════════════════════════════════════════════════════════════
#              FINGERPRINT STORE  (pluggable storage backend)
# ═══════════════════════════════════════════════════════════════════════════
#
# Switch backend by setting the FINGERPRINT_BACKEND env var:
#
#   FINGERPRINT_BACKEND=sqlite        → fingerprints.db   (default / dev)
#   FINGERPRINT_BACKEND=azure_table   → Azure Table Storage (production)
#
# Azure Table Storage also requires ONE of:
#   AZURE_STORAGE_CONNECTION_STRING
#   AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY
#
# Optional:
#   AZURE_TABLE_NAME   (default: "fingerprints")
#   SQLITE_DB_PATH     (default: "fingerprints.db")
# ════════════════════════════════════════════════════════════════════════════

class FingerprintStore(ABC):
    """Abstract fingerprint storage backend."""

    @abstractmethod
    def list_entries(self, vendor: Optional[str] = None) -> List[Dict]:
        """Return all fingerprint entries, optionally filtered by vendor."""
        ...

    @abstractmethod
    def save_entry(self, entry: Dict) -> None:
        """Persist a new fingerprint entry."""
        ...


class SQLiteFingerprintStore(FingerprintStore):
    """
    Local development backend — SQLite database (fingerprints.db).

    Handles concurrent writes safely via SQLite's WAL mode, and queries by
    vendor using an index instead of filtering a Python list.

    Table: fingerprints
    ┌──────────────────┬──────────────────────────────────────────────────────┐
    │ Column           │ Notes                                                │
    ├──────────────────┼──────────────────────────────────────────────────────┤
    │ hash (PK)        │ 16-char SHA256 — O(1) exact lookup                   │
    │ vendor           │ indexed — fast vendor-scoped queries                 │
    │ name             │ human-readable identifier                            │
    │ rule_file        │ relative path  e.g. "verizon/rule_verizon_2026.json" │
    │ sample_pages     │ JSON array stored as TEXT  e.g. "[3, 4, 5]"         │
    │ fingerprint_json │ full fingerprint dict serialised as JSON TEXT        │
    │ created_at       │ ISO-8601 timestamp                                   │
    └──────────────────┴──────────────────────────────────────────────────────┘

    In-process cache
    ────────────────
    Entries are loaded once per vendor per run and cached so that 13,000
    subscriber groups result in one DB query per vendor, not 13,000.
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS fingerprints (
            hash             TEXT PRIMARY KEY,
            vendor           TEXT NOT NULL,
            name             TEXT NOT NULL,
            rule_file        TEXT NOT NULL,
            sample_pages     TEXT NOT NULL DEFAULT '[]',
            fingerprint_json TEXT NOT NULL,
            created_at       TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vendor ON fingerprints(vendor);
    """

    def __init__(self, db_path: str = SQLITE_DB_PATH):
        self._db_path = db_path
        self._cache: Dict[str, List[Dict]] = {}  # vendor_key → List[entry]
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as con:
            con.executescript(self._DDL)
        logger.info(
            f"Fingerprint backend: SQLite ({self._db_path})"
        )

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> Dict:
        return {
            "name":         row["name"],
            "rule_file":    row["rule_file"],
            "sample_pages": json.loads(row["sample_pages"]),
            "created_at":   row["created_at"],
            "fingerprint":  json.loads(row["fingerprint_json"]),
        }

    def list_entries(self, vendor: Optional[str] = None) -> List[Dict]:
        cache_key = vendor or "__all__"
        if cache_key in self._cache:
            return self._cache[cache_key]
        with self._conn() as con:
            if vendor:
                rows = con.execute(
                    "SELECT * FROM fingerprints WHERE vendor = ?", (vendor,)
                ).fetchall()
            else:
                rows = con.execute("SELECT * FROM fingerprints").fetchall()
        entries = [self._row_to_entry(r) for r in rows]
        self._cache[cache_key] = entries
        logger.info(
            f"  Loaded {len(entries)} fingerprint(s) from SQLite "
            f"(vendor={vendor or 'all'}) → cached"
        )
        return entries

    def save_entry(self, entry: Dict) -> None:
        fp     = entry["fingerprint"]
        vendor = entry.get("vendor") or fp.get("vendor_hint") or "unknown"
        with self._conn() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO fingerprints
                    (hash, vendor, name, rule_file, sample_pages,
                     fingerprint_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fp["hash"],
                    vendor,
                    entry["name"],
                    entry["rule_file"],
                    json.dumps(entry.get("sample_pages", [])),
                    json.dumps(fp),
                    entry.get("created_at", datetime.now().isoformat()),
                ),
            )
        # Invalidate cache for this vendor
        self._cache.pop(vendor,    None)
        self._cache.pop("__all__", None)
        logger.info(
            f"Fingerprint saved (SQLite): '{entry['name']}' "
            f"vendor='{vendor}'  hash='{fp['hash']}'"
        )


class AzureTableFingerprintStore(FingerprintStore):
    """
    Production backend — Azure Table Storage.

    Schema
    ──────
    Table      : AZURE_TABLE_NAME  (default: "fingerprints")
    PartitionKey: vendor_hint      (e.g. "verizon", "att", "unknown")
    RowKey      : fingerprint hash (16-char SHA256 prefix)

    Extra columns stored per entity
    ───────────────────────────────
    name              string
    rule_file         string
    sample_pages      JSON string  (e.g. "[3, 4, 5]")
    created_at        ISO-8601 string
    fingerprint_json  full fingerprint dict serialised as JSON string

    In-process cache
    ────────────────
    Entries are cached per vendor key after the first query so that
    ~13,000 subscriber groups in one run result in at most ONE Table
    Storage query per vendor (instead of 13,000 queries).

    New entries invalidate the relevant cache key so the next call
    for that vendor sees the fresh data.

    Required env vars (one of)
    ──────────────────────────
    AZURE_STORAGE_CONNECTION_STRING
    AZURE_STORAGE_ACCOUNT_NAME  +  AZURE_STORAGE_ACCOUNT_KEY
    """

    _TABLE_NAME = os.getenv("AZURE_TABLE_NAME", "fingerprints")

    def __init__(self):
        self._cache: Dict[str, List[Dict]] = {}  # vendor_key → List[entry]
        self._client = self._make_client()

    def _make_client(self):
        try:
            from azure.data.tables import TableServiceClient  # type: ignore
            from azure.identity import DefaultAzureCredential  # type: ignore
        except ImportError:
            raise ImportError(
                "azure-data-tables and azure-identity are required for the Azure Table Storage backend.\n"
                "Install with: pip install azure-data-tables azure-identity"
            )
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if conn_str:
            svc = TableServiceClient.from_connection_string(
                conn_str,
                logging_enable=False,
                connection_timeout=10,
                read_timeout=60,
            )
        else:
            # Use managed identity with DefaultAzureCredential (production/secure)
            account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
            if not account:
                raise EnvironmentError(
                    "Azure Table Storage backend requires AZURE_STORAGE_ACCOUNT_NAME environment variable"
                )
            svc = TableServiceClient(
                endpoint=f"https://{account}.table.core.windows.net",
                credential=DefaultAzureCredential(),
                logging_enable=False,
                connection_timeout=10,
                read_timeout=60,
            )
        svc.create_table_if_not_exists(self._TABLE_NAME, logging_enable=False)
        logger.info(f"Fingerprint backend: Azure Table Storage (table='{self._TABLE_NAME}')")
        return svc.get_table_client(self._TABLE_NAME, logging_enable=False)

    @staticmethod
    def _entity_to_entry(entity: Dict) -> Dict:
        """Convert a flat Table Storage entity back to an entry dict."""
        return {
            "name":         entity["name"],
            "rule_file":    entity["rule_file"],
            "sample_pages": json.loads(entity.get("sample_pages", "[]")),
            "created_at":   entity.get("created_at", ""),
            "fingerprint":  json.loads(entity["fingerprint_json"]),
        }

    def list_entries(self, vendor: Optional[str] = None) -> List[Dict]:
        cache_key = vendor or "__all__"
        if cache_key in self._cache:
            return self._cache[cache_key]

        filter_str = f"PartitionKey eq '{vendor}'" if vendor else None
        entities   = self._client.query_entities(query_filter=filter_str)
        entries    = [self._entity_to_entry(e) for e in entities]
        self._cache[cache_key] = entries
        logger.info(
            f"  Loaded {len(entries)} fingerprint(s) from Azure Table Storage "
            f"(vendor={vendor or 'all'}) → cached"
        )
        return entries

    def save_entry(self, entry: Dict) -> None:
        fp     = entry["fingerprint"]
        vendor = entry.get("vendor") or fp.get("vendor_hint") or "unknown"
        entity = {
            "PartitionKey":     vendor,
            "RowKey":           fp["hash"],
            "name":             entry["name"],
            "rule_file":        entry["rule_file"],
            "sample_pages":     json.dumps(entry.get("sample_pages", [])),
            "created_at":       entry.get("created_at", datetime.now().isoformat()),
            "fingerprint_json": json.dumps(fp),
        }
        self._client.upsert_entity(entity)
        # Invalidate cache so next list_entries() re-fetches
        self._cache.pop(vendor,    None)
        self._cache.pop("__all__", None)
        logger.info(
            f"Fingerprint saved (Azure Table): '{entry['name']}' "
            f"partition='{vendor}'  row='{fp['hash']}'"
        )


def _make_fingerprint_store() -> FingerprintStore:
    """Factory — reads FINGERPRINT_BACKEND env var."""
    backend = os.getenv("FINGERPRINT_BACKEND", "sqlite").lower()
    if backend == "azure_table":
        return AzureTableFingerprintStore()
    # Default: sqlite
    return SQLiteFingerprintStore(SQLITE_DB_PATH)


# Module-level singleton — one store per process, shared across all calls.
_fp_store: Optional[FingerprintStore] = None


def _get_fp_store() -> FingerprintStore:
    global _fp_store
    if _fp_store is None:
        _fp_store = _make_fingerprint_store()
    return _fp_store


# ── Public fingerprint API (unchanged call signatures) ───────────────────

def match_fingerprint(
    fingerprint: Dict,
    threshold: float = 0.9,
    vendor: Optional[str] = None,
) -> Optional[Dict]:
    """
    Match fingerprint against known formats.

    If vendor is supplied, only entries whose name starts with that vendor
    prefix are considered — preventing cross-vendor false positives.

    Returns matching entry if similarity >= threshold, else None.
    """
    store   = _get_fp_store()
    entries = store.list_entries(vendor=vendor)

    if vendor:
        logger.info(
            f"  Fingerprint search scoped to vendor '{vendor}' "
            f"({len(entries)} candidate(s))"
        )

    best_match: Optional[Dict] = None
    best_score: float          = 0.0

    for entry in entries:
        score = calculate_similarity(fingerprint, entry["fingerprint"])
        if score > best_score:
            best_score = score
            best_match = entry

    if best_score >= threshold:
        logger.info(
            f"✓ KNOWN FORMAT matched: '{best_match['name']}' "
            f"(similarity: {best_score:.2%}, rule: {best_match['rule_file']})"
        )
        return best_match

    logger.info(
        f"✗ UNKNOWN FORMAT (best match: {best_score:.2%}, "
        f"threshold: {threshold:.2%})"
    )
    return None


def save_fingerprint(
    fingerprint: Dict,
    name: str,
    rule_file: str,
    sample_pages: List[int],
    vendor: Optional[str] = None,
) -> None:
    """Persist a new fingerprint entry via the active store backend."""
    entry = {
        "name":         name,
        "rule_file":    rule_file,
        "fingerprint":  fingerprint,
        "sample_pages": sample_pages,
        "created_at":   datetime.now().isoformat(),
        "vendor":       vendor or fingerprint.get("vendor_hint") or "unknown",
    }
    _get_fp_store().save_entry(entry)


# ═══════════════════════════════════════════════════════════════════════════
#                RULE STORE  (pluggable rule file backend)
# ═══════════════════════════════════════════════════════════════════════════
#
# Why a separate store for rules?
#   Azure Table Storage has a hard 64 KB per-property limit — rule JSON files
#   easily exceed this.  Rules live on the filesystem (LocalRuleStore).
#
# The same LocalRuleStore is used in dev and production.
# Switch path by setting RULES_DIR:
#
#   RULES_DIR=rules          → local dev (default, relative to cwd)
#   RULES_DIR=/mnt/agentfiles/rules_cache     → Azure Files share mounted in Container App
#
# No code changes needed between environments — only RULES_DIR changes.
# ═══════════════════════════════════════════════════════════════════════════

class LocalRuleStore:
    """
    Filesystem backend — reads/writes under RULES_DIR.

    Works identically for:
      • Local dev       : RULES_DIR=rules  (default)
      • Azure Files mount: RULES_DIR=/mnt/agentfiles/rules_cache

    In-process cache avoids re-reading the same rule file for every
    subscriber group in a run.
    """

    def __init__(self, rules_dir: Path = RULES_DIR):
        self._dir   = rules_dir
        self._cache: Dict[str, Dict] = {}  # rule_file → parsed rules

    def _resolve(self, rule_file: str, vendor: Optional[str] = None) -> Path:
        """Same two-step search as resolve_rule_path."""
        direct = self._dir / rule_file
        if direct.exists():
            return direct
        if vendor and "/" not in rule_file and "\\" not in rule_file:
            vendor_path = self._dir / vendor / rule_file
            if vendor_path.exists():
                return vendor_path
        return direct

    def load(self, rule_file: str, vendor: Optional[str] = None) -> Dict:
        if rule_file in self._cache:
            return self._cache[rule_file]
        path = self._resolve(rule_file, vendor)
        with open(path, "r", encoding="utf-8") as fh:
            rules = json.load(fh)
        self._cache[rule_file] = rules
        logger.info(
            f"Loaded rules (local): {len(rules.get('fields', []))} fields  "
            f"← {path}"
        )
        return rules

    def save(self, rule_file: str, rules: Dict, sample_pages: List[int]) -> None:
        rules.setdefault("meta", {})["sample_pages"] = sample_pages
        path = self._dir / rule_file
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rules, fh, indent=2, ensure_ascii=False)
        self._cache[rule_file] = rules
        logger.info(f"✓ Rules saved (local) → {path}")

    def exists(self, rule_file: str, vendor: Optional[str] = None) -> bool:
        return self._resolve(rule_file, vendor).exists()


# Module-level singleton — one rule store per process.
_rule_store: Optional[LocalRuleStore] = None


def _get_rule_store() -> LocalRuleStore:
    global _rule_store
    if _rule_store is None:
        _rule_store = LocalRuleStore(RULES_DIR)
        logger.info(f"Rule store: LocalRuleStore (RULES_DIR={RULES_DIR})")
    return _rule_store


# ═══════════════════════════════════════════════════════════════════════════
#                   3. RULE-BASED EXTRACTOR (Known Layouts)
# ═══════════════════════════════════════════════════════════════════════════

def load_rules(rule_file: str, vendor: Optional[str] = None) -> Dict:
    """Load rule dict via the active rule store backend."""
    return _get_rule_store().load(rule_file, vendor=vendor)


def resolve_rule_path(rule_file: str, vendor: Optional[str] = None) -> Path:
    """
    Resolve a rule_file name (as stored in the fingerprint entry) to its
    full filesystem path under RULES_DIR.

    Search order — first existing path wins:
      1. RULES_DIR / rule_file          — works for both
                                            new  : "verizon/rule_verizon_2026.json"
                                            legacy: "rule_verizon_2026.json"
      2. RULES_DIR / vendor / rule_file — migration helper: old flat entry
                                            whose file was manually moved to a
                                            vendor subfolder after the fact

    If neither exists the direct path is returned and the caller decides
    whether to raise or fall back to LLM generation.
    """
    direct = RULES_DIR / rule_file
    if direct.exists():
        return direct

    # Try vendor subfolder for bare filenames (no path separator)
    if vendor and "/" not in rule_file and "\\" not in rule_file:
        vendor_path = RULES_DIR / vendor / rule_file
        if vendor_path.exists():
            logger.info(
                f"  Rule '{rule_file}' not found flat; "
                f"resolved via vendor subfolder '{vendor}/'"
            )
            return vendor_path

    # Return direct path regardless — let caller handle missing file
    return direct


def _coerce(value: str, value_type: str) -> Any:
    """Convert extracted string to target type."""
    v = value.strip()
    try:
        if value_type in ("currency", "float"):
            # Handle both US (1,234.56) and European (1.234,56) formats
            if re.search(r'\d{1,3}(?:\.\d{3})+,\d{1,2}$', v) or re.search(r'^\d{1,3},\d{2}$', v):
                v_norm = v.replace(".", "").replace(",", ".")
            else:
                v_norm = v.replace(",", "")
            return float(re.sub(r"[^\d.-]", "", v_norm) or "0")
        if value_type == "integer":
            return int(re.sub(r"[^\d]", "", v) or "0")
        if value_type == "date":
            return v
    except (ValueError, TypeError):
        pass
    return v


def _anchor_matches(word_text: str, anchor: str) -> bool:
    """Fuzzy match a word against an anchor label."""
    wl = word_text.lower().strip()
    al = anchor.lower().strip()
    if wl == al:
        return True
    al_compact = re.sub(r"\s+", "", al)
    wl_compact = re.sub(r"\s+", "", wl)
    if al_compact in wl_compact or wl_compact in al_compact:
        return True
    first_token = al.split()[0]
    if wl.startswith(first_token):
        return True
    return False


def _words_near_anchor(
    words: List[Dict],
    anchor: str,
    tol_x: float,
    tol_y: float,
    offset_x: float,
    offset_y: float,
    max_dist: float,
    direction: str,
) -> List[Dict]:
    """Find words spatially adjacent to anchor."""
    anchor_words = [w for w in words if _anchor_matches(w["text"], anchor)]
    if not anchor_words:
        return []
    
    ref = anchor_words[0]
    results = []
    
    for w in words:
        if w is ref:
            continue
        if direction == "right":
            if (
                abs(w["y0"] - ref["y0"]) <= tol_y
                and w["x0"] >= ref["x1"] - tol_x
                and w["x0"] - ref["x1"] <= max_dist
            ):
                results.append(w)
        elif direction == "below":
            if (
                abs(w["x0"] - ref["x0"]) <= tol_x
                and w["y0"] >= ref["y1"] - tol_y
                and w["y0"] - ref["y1"] <= max_dist
            ):
                results.append(w)
    
    if direction == "right":
        results.sort(key=lambda w: w["x0"])
    else:
        results.sort(key=lambda w: (w["y0"], w["x0"]))
    
    return results


def _apply_strategy_anchor_right(field: Dict, words: List[Dict]) -> str:
    """Extract value to the RIGHT of anchor label."""
    matches = _words_near_anchor(
        words, field.get("anchor_text", ""),
        field.get("anchor_tolerance_x", 5),
        field.get("anchor_tolerance_y", 5),
        field.get("value_offset_x", 0),
        field.get("value_offset_y", 0),
        field.get("max_distance", 200),
        "right",
    )
    return " ".join(w["text"] for w in matches)


def _apply_strategy_anchor_below(field: Dict, words: List[Dict]) -> str:
    """Extract value BELOW anchor label."""
    matches = _words_near_anchor(
        words, field.get("anchor_text", ""),
        field.get("anchor_tolerance_x", 5),
        field.get("anchor_tolerance_y", 5),
        field.get("value_offset_x", 0),
        field.get("value_offset_y", 0),
        field.get("max_distance", 200),
        "below",
    )
    return " ".join(w["text"] for w in matches)


def _apply_strategy_region(field: Dict, words: List[Dict]) -> str:
    """Extract words within region_bbox."""
    bbox = field.get("region_bbox")
    if not bbox or len(bbox) < 4:
        return ""
    x0, y0, x1, y1 = bbox
    region_words = [
        w for w in words
        if w["x0"] >= x0 and w["y0"] >= y0 and w["x1"] <= x1 and w["y1"] <= y1
    ]
    region_words.sort(key=lambda w: (w["y0"], w["x0"]))
    return " ".join(w["text"] for w in region_words)


def _apply_strategy_regex(field: Dict, full_text: str) -> str:
    """Extract value using regex pattern."""
    pattern = field.get("regex_pattern", "")
    if not pattern:
        return ""
    match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return ""


def _apply_strategy_table_cell(field: Dict, tables: List[List]) -> str:
    """Extract value from table cell."""
    row_i = field.get("table_row", 0)
    col_i = field.get("table_col", 0)
    for table in tables:
        if row_i < len(table) and table[row_i] and col_i < len(table[row_i]):
            cell = table[row_i][col_i]
            return str(cell).strip() if cell else ""
    return ""


# ─────────────────── Regex fallbacks for common currency/numeric fields ─────

# ── Fields where a 1-3 digit bare number is almost certainly a charge
# line-item ordinal (e.g. "6.", "13") rather than a real usage value.
# When a primary strategy extracts such a value, it is discarded and
# the fallback patterns below are tried instead.
_LINE_ITEM_CONTAMINATION_FIELDS = {
    "voice_minutes_used",
    "messages_sent",
    "data_usage_used",
    "voice_minutes_included",
    "messages_included",
    "data_usage_included",
    "subscriber_name",
    "plan_name",
    "monthly_access_charge",
}

# Fallback regex patterns tried when the primary rule strategy fails (or returns
# a contaminated value).  A field may have a list of patterns — each is tried
# in order and the first non-empty match wins.
#
# AT&T usage-sidebar layout (from pdfplumber text extraction):
#   …MobSel Spec BEST Pooled 3GB 5G 185         ← voice used at end of line
#   iPhone w/VVM (unlimited)                      ← voice included in parens
#   Call over Wi-Fi 157
#   UNL DOM Messaging (unlimited) 8              ← messages used after the paren
#   MobSel Spec BEST Pool 3GB 5G 1,019,256       ← data used at end of line
#   iPhone VVM (3,145,728 KB)                    ← data included in parens
#   Additional Data* (1,024 MB) 1,024            ← overflow bucket
#
# Daytime-minutes plans (some AT&T lines):
#   Daytime minutes 11
#   Night & Weekend minutes 12
#
# Design: split into two dicts so the fallback loop only runs vendor-specific
# patterns when the current PDF's vendor matches — avoids O(vendors×fields×patterns)
# growth as new carriers are added.  Add a new key to _FIELD_REGEX_FALLBACKS_VENDOR
# for each new carrier; _FIELD_REGEX_FALLBACKS_COMMON holds truly generic patterns.

# ── Vendor-agnostic fallbacks (billing summary only) ─────────────────────────
_FIELD_REGEX_FALLBACKS_COMMON: Dict[str, Any] = {
    "billing_period":         r"Bil(?:ling)?\s*[Pp]eri(?:od)?[:\s]+([A-Za-z0-9/\-\s]+?)\s{2,}",
    "due_date":               r"[Dd]u(?:e)?\s*[Dd]ate[:\s]+([A-Za-z0-9/\-\s,]+?)\s{2,}",
    "usage_charges_subtotal": r"[Uu]sage\s*and\s*[Pp]urchas[eE]?\s*[Cc]harge[s]?\s+\$(\d[\d,\.]*)",
    "surcharges_subtotal":    r"[Ss]urcharg[eE]?\s*and\s*[Oo]ther[:\s]+\$(\d[\d,\.]*)",
    "taxes_and_fees_subtotal":r"[Tt]ax(?:es)?[,\s]*[Gg]ov(?:ernment)?[:\s]+\$(\d[\d,\.]*)",
    "total_current_charges":  r"[Tt]ot(?:al)?\s*[Cc]urr(?:ent)?\s*[Cc]harg[eE]?(?:s)?[^\d]*\$(\d[\d,\.]*)",
    "voice_overage_charge":   r"[Tt]otal\s*[Vv]oice\s+\$(\d[\d,\.]*)",
    "data_overage_charge":    r"[Tt]otal\s*[Dd]ata\s+\$(\d[\d,\.]*)",
    "messaging_charge":       r"[Tt]otal\s*[Mm]essaging\s+\$(\d[\d,\.]*)",
}

# ── Vendor-specific fallbacks — add one key per carrier ──────────────────────
_FIELD_REGEX_FALLBACKS_VENDOR: Dict[str, Dict[str, Any]] = {
    # ── AT&T ─────────────────────────────────────────────────────────────────
    "att": {
        # Subscriber identity
        # Header format: "ne, 201.213.7308        \n      JAN REINBACHER      \n"
        "phone_number":    r"ne,\s+([\d.]+)",
        "subscriber_name": r"ne,\s+[\d.]+[^\n]*\n\s*([A-Z][A-Z '.\-]+?)\s*\n",

        # Plan details — "4. MobSel Spec BEST Pooled 3GB 5G iPhone w/VVM $70.00"
        "plan_name": [
            r"^\s*\d+\.\s+((?:Mob[Ss]el|Mobile\s+Slct?)\s+Spec\s[^\n$]+?)\s+\$[\d.]",
            r"^\s*1\.\s+([^\n$]+?)\s+\$[\d.]",
        ],
        "monthly_access_charge": [
            r"(?:Mob[Ss]el|Mobile\s+Slct?)\s+Spec\s[^\n$]+?\$([\d.]+)",
            r"^\s*1\.\s+[^\n$]+?\$([\d.]+)",
        ],

        # Voice usage — actual pdfplumber text stream (documented from live extraction):
        #   …MobSel Spec BEST Pooled 3GB 5G 185     ← voice used AT END OF PLAN LINE
        #   iPhone w/VVM (unlimited)                 ← voice included in parens, NEXT line
        #   UNL DOM Messaging (unlimited) 8          ← messages used AFTER (unlimited)
        #   MobSel Spec BEST Pool 3GB 5G 1,019,256  ← data used AT END OF PLAN LINE
        #   iPhone VVM (3,145,728 KB)                ← data included in parens
        #   Additional Data* (1,024 MB) 1,024        ← overflow bucket
        #
        # Two-column layout (e.g. page with Monthly charges left + Usage summary right):
        #   pdfplumber interleaves by Y; sidebar rows merge with left-col rows.
        #   "-$43.50  MobSel Spec BEST Pooled 3GB 5G  8" on same text line.
        #   The GREEDY [^\n]+ in the MobSel pattern backtracks to the LAST number.
        "voice_minutes_used": [
            # PRIMARY — greedy [^\n]+ captures everything up to last number before w/VVM
            # Works for both single-column (plain) and two-column (interleaved) layouts.
            r"Mob[Ss]el\s+Spec\b[^\n]+\s([\d,]+)\s*\n[^\n]*w/VVM",
            r"(?:Mob[Ss]el|Mobile)\s+Spec\b[^\n]+\s([\d,]+)(?=\s*\n[^\n]*(?:w/VVM|unlimited))",
            # Usage-Summary inline: "w/VVM (unlimited) 506" — number AFTER (unlimited)
            r"w/VVM\s+\(unlimited\)\s+([\d,]+)",
            # Talk-section anchor for two-column pages where the sidebar is NOT yet
            # merged with the left column (sidebar appended after left column in output)
            r"Talk\s+Used[\s\S]{0,500}?([\d,]+)\s*\n[^\n]*(?:w/VVM|\(unlimited\))",
            r"Talk\s+Used[\s\S]{0,400}?Mob[Ss]el[^\n]+\s([\d,]+)\s*\n",
            # Line-plan formats
            r"Daytime\s+minutes\s+\([^)]+\)\s+([\d,]+)",
            r"Night\s+&\s+Weekend\s+minutes[\s\S]{0,40}?([\d,]+)",
            r"Daytime\s+minutes\s+([\d,]+)",
            r"([\d,]+)\n[^\n]*w/VVM\s+\(unlimited\)",
            r"w/VVM\s+\((unlimited)\)",
            r"Daytime\s+minutes\s+\((unlimited|[\d,]+)\)",
        ],
        "voice_minutes_included": [
            r"Talk\s+Used[\s\S]{0,500}?\(unlimited\)",
            r"w/VVM\s+\((unlimited)\)",
            r"Daytime\s+minutes\s+\((unlimited|[\d,]+)\)",
        ],

        # SMS — "UNL DOM Messaging (unlimited) 2" — number always AFTER (unlimited)
        # on the SAME line (pdfplumber keeps this row intact).
        "messages_sent": [
            r"UNL\s+DOM\s+Messaging\s+\(unlimited\)\s+([\d,]+)",        # primary: same-line
            r"Text\s+Used[\s\S]{0,300}?\(unlimited\)\s+([\d,]+)",       # sidebar section anchor
            r"UNL\s+DOM\s+Messaging[\s\S]{0,60}?([\d,]+)",              # cross-line
            r"[Mm]essag\w*\s+\((?:unlimited|[\d,]+)\)\s+([\d,]+)",
            r"[Mm]essag\w*\s+\((unlimited|[\d,]+)\)",
        ],
        "messages_included": [
            r"Text\s+Used[\s\S]{0,300}?\(unlimited\)",
            r"[Mm]essag\w*\s+\((unlimited|[\d,]+)\)",
        ],

        # Total — AT&T per-subscriber footer: "Total for 201.209.8474   $33.17"
        # Phone may use dot (201.209.8474) or dash (201-247-4069) separators.
        # pdfplumber sometimes emits the right-column amount on the NEXT line, so
        # [^\$\n]* (which stops at \n) fails.  Use [^\d\n]+? (non-digit, non-newline
        # gap, non-greedy) for same-line, and an explicit \n variant for cross-line.
        "total_current_charges": [
            # same-line: any non-digit gap (spaces ± $) between phone and amount
            # handles: "...8474    $33.17"  AND  "...8474    33.17"
            r"[Tt]otal\s+for\s+[\d.\-]+[^\d\n]+?([\d,]+\.\d{2})(?!\d)",
            # cross-line: phone on one line, [$]amount on next
            # handles: "...8474\n$33.17"  AND  "...8474\n   33.17"
            r"[Tt]otal\s+for\s+[\d.\-]+\s*\n[^\d\n]*?([\d,]+\.\d{2})(?!\d)",
            # "Total Current Charges" label form (e.g. from LLM-generated rule miss)
            r"[Tt]ot(?:al)?\s*[Cc]urr(?:ent)?\s*[Cc]harg[eE]?(?:s)?[^\d]*\$([\d,\.]*\d)",
        ],

        # Data — pool plan: number before "VVM (plan KB)" line; overflow: "Additional Data*"
        "data_usage_used": [
            r"([\d,]+)\n[^\n]*VVM\s+\([\d,]+\s*KB\)",           # VVM pool older layout
            r"\bLTE\b[^(\n]*\([\d,]+\s*KB\)\s+([\d,]+)",        # LTE pool
            r"\bPool\b[^(\n]*\([\d,]+\s*KB\)\s+([\d,]+)",       # Pool (Usage Summary same-line)
            r"\bVVM\b[^(\n]*\([\d,]+\s*KB\)\s+([\d,]+)",        # VVM same-line (no Pool/LTE keyword)
            r"Additional\s+Data\*\s+\([^)]+\)\s+([\d,]+)",      # overflow bucket
        ],
        "data_usage_included": [
            r"VVM\s+\(([\d,]+\s*KB)\)",
            r"\b(?:LTE|Pool)\b[^(\n]+\(([\d,]+\s*KB)\)",
            r"(?<!Additional\s{1,4}Data)(?<!\*\s{1,10})\(([\d,]+\s*KB)\)",
            r"(?:included|allowance|plan)[^(\n]{0,40}\(([\d,]+\s*(?:MB|GB))\)",
        ],
    },

    # ── Verizon ───────────────────────────────────────────────────────────────
    "verizon": {
        "voice_minutes_used":  [r"(?:minut|min)[^0-9]*?(\d+)\s*(?:--|-|billa)"],
        "messages_sent":       [r"(?:messag)[^0-9]*?(\d+)\s*(?:--|-|billa)"],
        "data_usage_used":     [r"(?:gigabyt|gigab|GB)[^0-9]*?[\d.]+\s+(\d+\.\d+)\s*(?:--|-)"],
        # "Total Current Charges for 201-396-8407  $37.41"
        # "Total Current Charges for 219-869-0871.  $47.41"  (trailing period after phone)
        # [^\$]* skips phone digits and any trailing punctuation before the $ sign.
        "total_current_charges": [
            r"[Tt]otal\s+[Cc]urrent\s+[Cc]harges\s+for\s+[\d\-\.]+[^\$]*\$([\d,]+(?:\.\d+)?)",
        ],
    },

    # ── VIVO (Brazil) ─────────────────────────────────────────────────────────
    "vivo": {
        # GESTAO VOZ / VOZ row — Utilizado column: NNmNNs format (minutes+seconds)
        "voice_minutes_used": [
            # 1 — Subtotal of voice block e.g. "Subtotal Voz  03m06s"
            r"[Ss]ubtotal\s+(?:Voz|VOZ|GESTAO\s+VOZ)[^\n]*?(\d+\s*m\s*\d+\s*s)",
            r"(?:Voz|VOZ|GESTAO\s+VOZ)[^\n]*?[Ss]ubtotal[^\n]*?(\d+\s*m\s*\d+\s*s)",
            # 2 — GESTAO VOZ label, same line
            r"(?:GESTAO\s+VOZ)[^\n]*?(\d+\s*m\s*\d+\s*s)",
            # 3 — Per-phone summary row: label "Voz" followed by NNmNNs on same line
            r"^\s*Voz\s[^\n]*?(\d+\s*m\s*\d+\s*s)",
            r"\bVoz\b[^\n]*?(\d+\s*m\s*\d+\s*s)",
            # 4 — "Utilizado" header near VOZ label (pdfplumber may reorder columns)
            r"Utilizado[\s\S]{0,300}?(?:GESTAO\s+VOZ|\bVOZ\b|\bVoz\b)[\s\S]{0,300}?(\d+\s*m\s*\d+\s*s)",
            r"(?:GESTAO\s+VOZ|\bVOZ\b|\bVoz\b)[\s\S]{0,300}?Utilizado[\s\S]{0,300}?(\d+\s*m\s*\d+\s*s)",
            # 5 — Wide fallback
            r"(?:GESTAO\s+VOZ|\bVOZ\b)[\s\S]{0,1500}?(\d+\s*m\s*\d+\s*s)",
            # 6 — Last resort: NNmNNs is a VIVO-only format — any match in the page is voice
            r"(\d+\s*m\s*\d+\s*s)",
        ],
        # GESTAO DADOS / Internet / FRANQUIA INTERNET COMPARTILHADA row
        # Layout: FRANQUIA INTERNET COMPARTILHADA | 15,00GB (Incluso) | 2653MB 900KB (Utilizado)
        # The Incluso column is always in GB; the Utilizado column is in MB+KB.
        # Matching MB|KB explicitly skips the GB Incluso value and lands on the used value.
        "data_usage_used": [
            # 1 — Same-line match: look for MB/KB on same row as label (skips GB Incluso)
            r"(?:FRANQUIA\s+INTERNET\s+COMPARTILHADA|GESTAO\s+DADOS|\bInternet\b)[^\n]*([\d,.]+\s*(?:MB|KB)(?:\s+[\d,.]+\s*(?:MB|KB))*)",
            # 2 — Multi-line fallback: skip the GB token, capture MB/KB compound
            r"(?:FRANQUIA\s+INTERNET\s+COMPARTILHADA|GESTAO\s+DADOS|\bInternet\b)[\s\S]{0,100}?[\d,.]+\s*GB[\s\S]{0,100}?([\d,.]+\s*(?:MB|KB)(?:\s+[\d,.]+\s*(?:MB|KB))*)",
        ],
    },

    # ── Telekom (Germany) ─────────────────────────────────────────────────────
    "telekom": {
        # The grouping key is "Ihre Mobilfunk-Kartennummer" (matched by _PHONE_RE).
        # The ACTUAL subscriber phone number is "Rufnummer Telefonie (0151)11183612".
        # German format: (NNNN)NNNNNNNN — 4-digit area code, no separator.
        "phone_number": [
            r"Rufnummer\s+Telefonie\s+(\(\d{3,5}\)\d{6,9})",
            r"Rufnummer\s+Telefonie\s+(\d{3,5}[\s/\-]\d{6,9})",
        ],
        # Data usage total: "INSGESAMT VERBRAUCHTES DATENVOLUMEN  1.018.539 KB"
        # German dot-separated thousands: 1.018.539 KB → normaliser handles it.
        "data_usage_used": [
            r"INSGESAMT\s+VERBRAUCHTES\s+DATENVOLUMEN[^\n]*?([\d.,]+\s*(?:KB|MB|GB))",
        ],
    },

}

# ── Per-vendor fields that are ALWAYS re-run by the vendor fallback pattern ──
# even when the LLM rule already extracted a value. Add a new key per carrier;
# use an empty set() when no override is needed.
_VENDOR_ALWAYS_OVERRIDE: Dict[str, set] = {
    # Fields listed here are always re-extracted using vendor fallback patterns
    # even when the LLM rule already produced a value.  Only carriers that are
    # registered in _FIELD_REGEX_FALLBACKS_VENDOR need an entry here.
    "att":     {"total_current_charges"},  # LLM gets account-level total; need per-subscriber value
    "verizon": set(),
    "vivo":    {"voice_minutes_used"},
    "telekom": {"phone_number", "data_usage_used"},  # Kartennummer used for grouping; phone_number must come from Rufnummer Telefonie
}


def _run_fallback_patterns(patterns_or_str, full_text: str,
                           field_name: str = "", source_label: str = "") -> str:
    """Try each regex pattern against full_text; return first non-empty capture group or ''."""
    pats = [patterns_or_str] if isinstance(patterns_or_str, str) else patterns_or_str
    for _pat in pats:
        try:
            _m = re.search(_pat, full_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if _m:
                _v = next((g.strip() for g in _m.groups() if g is not None), "")
                if _v:
                    logger.debug(f"Field '{field_name}': {source_label} {_pat[:60]!r} → {_v!r}")
                    return _v
        except Exception as _exc:
            logger.debug(f"Field '{field_name}' fallback regex error: {_exc}")
    return ""


# Pre-normalized vendor lookup tables — built once at module load.
# Avoids repeated re.sub() calls on the same constant strings on every extraction call.
_VNORM_FALLBACK: List[Tuple[str, str]] = [
    (re.sub(r'[&.\s]', '', k.lower()), k)
    for k in _FIELD_REGEX_FALLBACKS_VENDOR
]
_VNORM_DETECT: List[Tuple[str, str]] = [
    (re.sub(r'[&.\s]', '', alias.lower()), dk)
    for dk, aliases in _VENDOR_DETECT_KEYWORDS.items()
    for alias in [dk] + list(aliases)
]


def _resolve_vendor_key(vendor: Optional[str]) -> Optional[str]:
    """Return the canonical vendor key for a caller-supplied vendor string, or None.

    Resolution order:
      1. Match against _FIELD_REGEX_FALLBACKS_VENDOR keys (field-extraction dict).
      2. Match against _VENDOR_DETECT_KEYWORDS keys (detection-hint dict).
    Both lookups normalise the string (lowercase, strip '&', '.', spaces) before
    comparing so that all of these resolve correctly:
      'att', 'AT&T', 'at&t', 'AT&T Business'  → 'att'
      'telekom', 'T-Mobile', 'tmobile'          → 'telekom'
    """
    if not vendor:
        return None
    # Normalise: lowercase, strip & / . / spaces so "AT&T" → "att"
    _vl_norm = re.sub(r'[&.\s]', '', vendor.lower())

    # Pass 1 — match against field-extraction registry (pre-normalized at module load)
    for _vk_norm, _vk in _VNORM_FALLBACK:
        if _vk_norm in _vl_norm or _vl_norm in _vk_norm:
            return _vk

    # Pass 2 — match against detection-keyword aliases (pre-normalized at module load)
    # Handles 'telekom' / 't-mobile' / 'tmobile' → 'telekom', etc.
    for _alias_norm, _dk in _VNORM_DETECT:
        if _alias_norm in _vl_norm or _vl_norm in _alias_norm:
            return _dk

    return None


def extract_fields(words: List[Dict], full_text: str, tables: List, rules: Dict, vendor: Optional[str] = None) -> Dict:
    """
    Apply every field rule in rule.json and return a flat dict of extracted values.

    For each field the extraction is attempted in priority order:
      1. Primary strategy declared in the rule (regex, region, anchor_right,
         anchor_below, or table_cell).
      2. Cross-fallback: if regex returns empty and region_bbox exists, try
         region — and vice versa.
      3. Vendor-specific then common _FIELD_REGEX_FALLBACKS as a last resort.
      4. Second-pass: same fallbacks for fields entirely absent from the rule.

    Values are coerced to the declared value_type (currency, float, integer,
    date, or string) before being stored in the output dict.
    """
    record: Dict[str, Any] = {}

    for field in rules.get("fields", []):
        name     = field.get("field_name", "unknown")
        strategy = field.get("strategy", "regex")
        vtype    = field.get("value_type", "string")
        raw      = ""

        try:
            if strategy == "anchor_right":
                raw = _apply_strategy_anchor_right(field, words)
            elif strategy == "anchor_below":
                raw = _apply_strategy_anchor_below(field, words)
            elif strategy == "region":
                raw = _apply_strategy_region(field, words)
                # ── If region returned nothing, try regex_pattern from the rule ──
                if not raw and field.get("regex_pattern"):
                    raw = _apply_strategy_regex(field, full_text)
                    if raw:
                        logger.debug(f"Field '{name}': region empty, used rule regex → {raw!r}")
            elif strategy == "regex":
                raw = _apply_strategy_regex(field, full_text)
                # ── If regex returned nothing, try region_bbox from the rule ─────
                if not raw and field.get("region_bbox"):
                    raw = _apply_strategy_region(field, words)
                    if raw:
                        logger.debug(f"Field '{name}': regex empty, used rule region → {raw!r}")
            elif strategy == "table_cell":
                raw = _apply_strategy_table_cell(field, tables)
            else:
                logger.warning(f"Unknown strategy '{strategy}' for field '{name}'")
        except Exception as exc:
            logger.debug(f"Field '{name}' extraction error: {exc}")

        # ── Contamination / validation checks ─────────────────────────────────
        # Clear raw when the primary strategy returns a clearly wrong value,
        # so the regex fallback gets a chance to run.
        if raw:
            raw_s = str(raw).strip()

            # 1. Line-item ordinals (e.g. "6", "13.") in usage/name fields
            if name in _LINE_ITEM_CONTAMINATION_FIELDS:
                if re.fullmatch(r'\d{1,3}\.?', raw_s):
                    logger.debug(f"Field '{name}': discarding ordinal {raw!r}")
                    raw = ""

            # 1b. Currency-style values (e.g. "70.00", "43.50") in usage count fields.
            #     AT&T two-column layout: LLM rule can land on plan charge amount
            #     for voice_minutes_used / messages_sent.  Discard NN.NN values.
            if raw and name in {"voice_minutes_used", "messages_sent"}:
                if re.fullmatch(r'\d+\.\d{2}', raw_s):
                    logger.debug(f"Field '{name}': discarding currency-like value {raw!r}")
                    raw = ""

            # 2. Numeric-expected fields that contain no digit at all
            #    (e.g. LLM returned column header "Used KB", "Used", "unlimited",
            #    or label text "for", "Used" for included-allowance fields)
            if raw and name in {
                "voice_minutes_used", "data_usage_used",
                "messages_sent", "monthly_access_charge",
                "data_usage_included", "voice_minutes_included", "messages_included",
            }:
                if not re.search(r'\d', raw_s):
                    logger.debug(f"Field '{name}': discarding label-only value {raw!r}")
                    raw = ""

            # 3. phone_number: must look like a phone number.
            #    If the extracted value contains a phone PLUS extra garbage text
            #    (e.g. "201.268.4267 Tax -"), trim to just the phone portion.
            if raw and name == "phone_number":
                m = _PHONE_RE.search(raw_s)
                if m:
                    if len(m.group(0).strip()) < len(raw_s):
                        # extra text present — trim to phone-only
                        raw = m.group(0).strip()
                        logger.debug(f"Field 'phone_number': trimmed to {raw!r}")
                else:
                    logger.debug(f"Field 'phone_number': discarding non-phone value {raw!r}")
                    raw = ""

            # 4. plan_name: must contain a recognisable plan keyword
            #    (rejects line-item labels like "Custom International Daily Fee")
            if raw and name == "plan_name":
                if not re.search(
                    r'Spec|Pool|Slct|Select|Mobile|Mob[Ss]el|LTE|VVM|Unlimited|Share',
                    raw_s, re.IGNORECASE
                ):
                    logger.debug(f"Field 'plan_name': discarding non-plan value {raw!r}")
                    raw = ""

        # ── Regex fallback when primary strategy returned nothing ─────────────
        # 1. Vendor-specific patterns first (only runs patterns for matched vendor)
        # 2. Common (billing) patterns second
        _vendor_key = _resolve_vendor_key(vendor)
        if not raw:
            if _vendor_key and name in _FIELD_REGEX_FALLBACKS_VENDOR[_vendor_key]:
                raw = _run_fallback_patterns(
                    _FIELD_REGEX_FALLBACKS_VENDOR[_vendor_key][name],
                    full_text, name, f"vendor({_vendor_key}) fallback",
                )
        if not raw and name in _FIELD_REGEX_FALLBACKS_COMMON:
            raw = _run_fallback_patterns(
                _FIELD_REGEX_FALLBACKS_COMMON[name],
                full_text, name, "common fallback",
            )

        record[name] = _coerce(raw, vtype) if raw else ""

    # ── Second-pass: fallbacks for fields ABSENT from the rule ───────────────
    # Runs vendor-specific + common fallback patterns for any canonical field
    # that the LLM-generated rule omitted entirely.
    # Currently enabled for AT&T (per-subscriber fields always absent from
    # page-1 rule) and Verizon (total_current_charges label embeds phone
    # number so the common regex silently fails).
    if _vendor_key in _FIELD_REGEX_FALLBACKS_VENDOR:  # runs for any registered vendor
        _absent_vendor_fields = set(_FIELD_REGEX_FALLBACKS_VENDOR.get(_vendor_key, {}).keys())
        _all_fallback_fields = _absent_vendor_fields | set(_FIELD_REGEX_FALLBACKS_COMMON.keys())

        # Fields driven by _VENDOR_ALWAYS_OVERRIDE — no if-branches needed when
        # adding new carriers; just update the dict above.
        _ALWAYS_OVERRIDE_VENDOR = _VENDOR_ALWAYS_OVERRIDE.get(_vendor_key, set())

        for _fname in _all_fallback_fields:
            # Always seed the key so the CSV column appears even on a miss.
            if _fname not in record:
                record[_fname] = ""

            # Skip if already filled — UNLESS this field must always use the
            # vendor-specific pattern (e.g. AT&T per-subscriber total).
            if record.get(_fname) and _fname not in _ALWAYS_OVERRIDE_VENDOR:
                continue

            _fraw = ""
            if _fname in _FIELD_REGEX_FALLBACKS_VENDOR.get(_vendor_key, {}):
                _fraw = _run_fallback_patterns(
                    _FIELD_REGEX_FALLBACKS_VENDOR[_vendor_key][_fname],
                    full_text, _fname, f"2nd-pass vendor({_vendor_key}) fallback",
                )
            if not _fraw and _fname in _FIELD_REGEX_FALLBACKS_COMMON:
                _fraw = _run_fallback_patterns(
                    _FIELD_REGEX_FALLBACKS_COMMON[_fname],
                    full_text, _fname, "2nd-pass common fallback",
                )
            if _fraw:
                record[_fname] = _fraw
    # ─────────────────────────────────────────────────────────────────────────

    # Fix common artefacts left by LLM rules before returning.
    for fname, fval in list(record.items()):
        if not fval:
            continue
        v = str(fval).strip()

        # a) Strip wrapping parentheses  e.g. "(3,145,728 KB)" → "3,145,728 KB"
        v = re.sub(r'^\(([^)]+)\)$', r'\1', v).strip()

        # b) subscriber_name: keep only the first line
        #    (LLM sometimes returns "JAN REINBACHER\nActivity since last bill Dec")
        if fname == "subscriber_name" and '\n' in v:
            v = v.split('\n')[0].strip()

        # c) data_usage_used / data_usage_included: normalise to float MB.
        #    Converts any KB / MB / GB value to MB (float, no unit suffix).
        #    Also handles bare AT&T KB values (>100 000) and Verizon decimal GB.
        if fname in ("data_usage_used", "data_usage_included"):
            record[fname] = _normalize_data_usage(v)
            continue

        record[fname] = v

    return record


def extract_line_items(words: List[Dict], full_text: str, rules: Dict) -> List[Dict]:
    """
    Extract repeating table rows (e.g. call detail, usage records) from the page.

    Works by:
      1. Finding the header row y-position using header_anchor_text.
      2. Optionally finding a stop row y-position using stop_anchor_text.
      3. Collecting all words between header and stop rows.
      4. Grouping words into horizontal lines (rows).
      5. For each row, assigning words to columns by x-centre proximity
         (each column has an x_center and x_tolerance defined in the rule).

    Returns a list of dicts, one per data row. Empty rows are skipped.
    """
    li_rules = rules.get("line_items", {})
    if not li_rules.get("enabled"):
        return []

    header_anchor = li_rules.get("header_anchor_text", "")
    stop_anchor   = li_rules.get("stop_anchor_text", "")
    h_tol         = li_rules.get("header_y_tolerance", 5)
    columns       = li_rules.get("columns", [])

    if not columns or not header_anchor:
        return []

    # ── Find header row y-position ───────────────────────────────────────────
    header_y: Optional[float] = None
    for w in words:
        if header_anchor.lower() in w["text"].lower():
            header_y = w["y0"]
            break

    if header_y is None:
        logger.debug("Line-item header anchor not found on this page.")
        return []

    # ── Find stop row y-position ─────────────────────────────────────────────
    stop_y: Optional[float] = None
    if stop_anchor:
        for w in words:
            if stop_anchor.lower() in w["text"].lower() and w["y0"] > header_y:
                stop_y = w["y0"]
                break

    # ── Collect data words between header and stop ───────────────────────────
    data_words = [
        w for w in words
        if w["y0"] > header_y + h_tol
        and (stop_y is None or w["y0"] < stop_y)
    ]

    if not data_words:
        return []

    # ── Group words into lines ───────────────────────────────────────────────
    data_words_sorted = sorted(data_words, key=lambda w: (w["y0"], w["x0"]))
    row_groups: List[List[Dict]] = []
    current_row: List[Dict]      = [data_words_sorted[0]]

    for w in data_words_sorted[1:]:
        if abs(w["y0"] - current_row[-1]["y0"]) <= 3:
            current_row.append(w)
        else:
            row_groups.append(sorted(current_row, key=lambda w: w["x0"]))
            current_row = [w]
    row_groups.append(sorted(current_row, key=lambda w: w["x0"]))

    # ── Map each word to its column by x-centre proximity ────────────────────
    line_items: List[Dict] = []

    for row in row_groups:
        if not row:
            continue

        item: Dict[str, Any] = {}
        for col in columns:
            col_name  = col.get("field_name", "col")
            x_center  = col.get("x_center",   0)
            x_tol     = col.get("x_tolerance", 40)
            vtype     = col.get("value_type",  "string")

            # Collect all words whose centre falls within ±x_tol of the column centre
            col_words = [
                w for w in row
                if abs(((w["x0"] + w["x1"]) / 2) - x_center) <= x_tol
            ]
            raw = " ".join(w["text"] for w in col_words)
            item[col_name] = _coerce(raw, vtype) if raw else ""

        # Only keep rows that have at least one non-empty cell
        if any(v != "" for v in item.values()):
            line_items.append(item)

    return line_items


# ═══════════════════════════════════════════════════════════════════════════
#              USAGE FIELD NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_voice_minutes(raw: str) -> int:
    """
    Convert any voice/minutes string to a plain integer.

    Examples:
      "325 min"   → 325
      "1,205"     → 1205
      "Unlimited" → 999
      "06m24s"    → 6   (VIVO format — truncate to whole minutes)
      "0"         → 0
    """
    raw = raw.strip()
    if not raw or raw.lower() in ("n/a", "-", "\u2014"):
        return 0
    if raw.lower() == "unlimited":
        return 999

    # VIVO format: "06m24s", "84m12s" — use re.search not re.match
    # so leading label text ("GESTAO VOZ ...") won't prevent the match.
    vivo = re.search(r"(\d+)\s*m\s*(\d+)\s*s", raw, re.IGNORECASE)
    if vivo:
        return int(vivo.group(1))

    # Strip any non-numeric suffix (min, minutes, Talk, etc.) and commas
    digits = re.sub(r"[^\d]", "", raw.split()[0])
    return int(digits) if digits else 0


def _normalize_messages(raw: str) -> int:
    """
    Convert any SMS/messages string to a plain integer.

    Examples:
      "145"       → 145
      "1,205"     → 1205
      "Unlimited" → 999
    """
    raw = raw.strip()
    if not raw or raw.lower() in ("n/a", "-", "\u2014"):
        return 0
    if raw.lower() == "unlimited":
        return 999
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else 0


# Data unit multipliers → normalise everything to MB
_DATA_UNIT_TO_MB: Dict[str, float] = {
    "kb":  1 / 1024,
    "mb":  1.0,
    "gb":  1024.0,
    "tb":  1024.0 * 1024,
}

_DATA_TOKEN_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(KB|MB|GB|TB)",
    re.IGNORECASE,
)


def _normalize_data_usage(raw: str) -> float:
    """
    Sum ALL valid «number + unit» data tokens and return the total in
    megabytes as a plain float (no unit suffix).

    This correctly handles compound VIVO values like "2653MB 900KB" by
    summing each component: 2653 MB + 900/1024 KB ≈ 2653.879 MB.

    Conversion:
      KB → divide by 1 024
      MB → as-is
      GB → multiply by 1 024

    Special cases:
      "0" / missing / "Unlimited" → 0.0
    """
    if not raw or raw.strip().lower() in ("0", "n/a", "-", "\u2014", "unlimited"):
        return 0.0

    matches = _DATA_TOKEN_RE.findall(raw)
    if not matches:
        # No recognisable unit — assume MB and strip non-numeric noise
        digits = re.sub(r"[^\d.]", "", raw.split()[0])
        return round(float(digits), 4) if digits else 0.0

    total_mb = 0.0
    for num_str, unit_str in matches:
        number    = float(num_str.replace(",", ""))
        unit      = unit_str.lower()
        total_mb += number * _DATA_UNIT_TO_MB.get(unit, 1.0)

    return round(total_mb, 4)


def _apply_usage_defaults(record: Dict) -> Dict:
    """
    Normalise and default all three usage fields:
      • voice_minutes_used  → int (0 if absent, 999 if unlimited)
      • messages_sent       → int (0 if absent, 999 if unlimited)
      • data_usage_used     → float MB value (0.0 if absent, no unit suffix)
    Guarantees consistent types across all subscribers regardless of what the
    invoice shows.
    """
    record["voice_minutes_used"] = _normalize_voice_minutes(
        str(record.get("voice_minutes_used") or "0")
    )
    record["messages_sent"] = _normalize_messages(
        str(record.get("messages_sent") or "0")
    )
    record["data_usage_used"] = _normalize_data_usage(
        str(record.get("data_usage_used") or "0")
    )
    return record


def extract_with_rules(layout_data: Dict, rule_file: str, vendor: Optional[str] = None) -> Dict:
    """
    Extract structured data using existing rules (KNOWN LAYOUT path).
    rule_file is a relative key e.g. "verizon/rule_verizon_2026.json".
    """
    logger.info("→ Using RULE-BASED EXTRACTOR (known layout)")
    
    rules = load_rules(rule_file, vendor=vendor)
    all_words = layout_data["all_words"]
    tables = layout_data["tables"]
    full_text = "\n".join(layout_data["full_text"])

    record = extract_fields(all_words, full_text, tables, rules, vendor=vendor)
    line_items = extract_line_items(all_words, full_text, rules)
    
    if line_items:
        record["_line_items"] = line_items
        record["_line_item_count"] = len(line_items)
    
    return record


# ═══════════════════════════════════════════════════════════════════════════
#                4. LLM SCHEMA GENERATOR (Unknown Layouts)
# ═══════════════════════════════════════════════════════════════════════════

def make_azure_openai_client() -> AzureOpenAI:
    """
    Build Azure OpenAI client from environment variables.

    The endpoint is an APIM gateway that requires the subscription key sent
    as the 'Ocp-Apim-Subscription-Key' header (in addition to / instead of
    the standard 'api-key' header that the AzureOpenAI SDK sends by default).
    This is injected as a default header on the underlying httpx.Client.

        AZURE_OPENAI_ENDPOINT          — required (APIM gateway URL)
        AZURE_OPENAI_API_KEY           — required (APIM subscription key)
        AZURE_OPENAI_DEPLOYMENT_NAME_GPT5 — deployment for schema generator
                                             (default: gpt-5)
        AZURE_OPENAI_API_VERSION       — hardcoded: 2024-08-01-preview
    """
    endpoint    = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key     = os.getenv("AZURE_OPENAI_API_KEY")
    api_ver     = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    if not endpoint or not api_key:
        raise EnvironmentError(
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set in .env"
        )

    # APIM requires the subscription key as 'Ocp-Apim-Subscription-Key'.
    # The AzureOpenAI SDK sends api_key as 'api-key' which APIM ignores → 401.
    # Passing it as a default header on the httpx client ensures APIM accepts it.
    http_client = httpx.Client(
        verify=False,
        timeout=httpx.Timeout(120.0, connect=10.0),
        headers={"Ocp-Apim-Subscription-Key": api_key},
    )

    return AzureOpenAI(
        api_key=api_key,
        api_version=api_ver,
        azure_endpoint=endpoint,
        http_client=http_client,
    )


# Module-level singleton — reuses the same httpx.Client across all LLM calls in a run,
# preventing one new connection object per unknown-layout page.
_openai_client: Optional[AzureOpenAI] = None


def _get_openai_client() -> AzureOpenAI:
    """Return the cached Azure OpenAI client, creating it on first call."""
    global _openai_client
    if _openai_client is None:
        _openai_client = make_azure_openai_client()
    return _openai_client


def group_words_into_lines(words: List[Dict], y_tolerance: float = 3.0) -> List[List[Dict]]:
    """Group words by vertical position into lines."""
    if not words:
        return []
    
    sorted_words = sorted(words, key=lambda w: (w.get("page_num", 1), w["y0"], w["x0"]))
    lines = []
    current_line = [sorted_words[0]]
    
    for word in sorted_words[1:]:
        same_page = word.get("page_num", 1) == current_line[-1].get("page_num", 1)
        if same_page and abs(word["y0"] - current_line[-1]["y0"]) <= y_tolerance:
            current_line.append(word)
        else:
            lines.append(sorted(current_line, key=lambda w: w["x0"]))
            current_line = [word]
    lines.append(sorted(current_line, key=lambda w: w["x0"]))
    return lines


def build_line_text(pages_data: List[Dict]) -> str:
    """Build spatial text representation for LLM.

    Format: [y=<y0>-<y1>]  <x0>-<x1>:<word>  ...

    All four bounding-box coordinates (x0, y0, x1, y1) are embedded per word
    so the LLM can derive region_bbox = [x0-2, y0-2, x1+2, y1+2] directly
    from this output without a separate JSON word list.
    """
    sections = []

    for pg in pages_data:
        lines = group_words_into_lines(pg["words"])
        result_lines = [
            f"=== PAGE {pg['page_num']} ({pg['width']:.0f}×{pg['height']:.0f} pt) ==="
        ]
        for line in lines:
            if not line:
                continue
            y0 = line[0]["y0"]
            y1 = max(w["y1"] for w in line)
            parts = [f"[y={y0:.0f}-{y1:.0f}]"]
            for w in line:
                parts.append(f"{w['x0']:.0f}-{w['x1']:.0f}:{w['text']}")
            result_lines.append("  ".join(parts))
        sections.append("\n".join(result_lines))

    return "\n\n".join(sections)


# ──────────────────────────── LLM JSON repair ───────────────────────────────

def _attempt_json_repair(raw: str) -> Optional[Dict]:
    """
    Best-effort repair of malformed or truncated LLM JSON.

    Strategy 1 (preferred): use the json-repair library, which handles
      - LLM-injected garbage text inside values  (e.g. "108. sopics 54.0")
      - Truncated / unclosed structures
      - Missing commas, unquoted keys, trailing commas, etc.

    Strategy 2 (fallback): manual truncation repair — find the last
      complete field object, close the fields array + root object.

    Returns the repaired dict on success, or None if all strategies fail.
    """
    # ── Strategy 1: json-repair library ──────────────────────────────────────
    if _JSON_REPAIR_AVAILABLE:
        try:
            repaired_str = _repair_json(raw, return_objects=False)
            result = json.loads(repaired_str)
            if isinstance(result, dict) and ("fields" in result or "meta" in result):
                return result
        except Exception as e:
            logger.debug(f"json-repair strategy failed: {e}")

    # ── Strategy 2: manual truncation repair ─────────────────────────────────
    try:
        last_close = raw.rfind("}")
        if last_close == -1:
            return None
        
        fields_start = raw.find('"fields"')
        if fields_start == -1:
            return None
            
        candidate = raw[:last_close + 1]
        
        if '"fields"' in candidate and candidate.count('[') > candidate.count(']'):
            truncate_pos = last_close
            
            open_brackets = candidate.count('[') - candidate.count(']')
            open_braces = candidate.count('{') - candidate.count('}')
            
            closing = ""
            if open_braces > 0:
                closing += "}" * (open_braces - 1)
            if open_brackets > 0:
                closing += "]" * open_brackets
            
            if '"line_items"' not in candidate:
                closing += ',"line_items":{"enabled":false,"header_anchor_text":null,' \
                          '"header_y_tolerance":5,"stop_anchor_text":null,' \
                          '"source_page_hint":null,"columns":[]}'
            
            closing += "}"
            
            result = json.loads(candidate + closing)
            if isinstance(result, dict) and ("fields" in result or "meta" in result):
                return result
    except Exception as e:
        logger.debug(f"Manual truncation repair failed: {e}")

    return None


_SYSTEM_PROMPT_BASE = """
You are a telecom / utility billing expert AND a data-extraction engineer.

You will receive word-level data extracted from one or more pages of a SAMPLE INVOICE.
Your task is to CREATE EXTRACTION RULES that will be used to extract data from
thousands of similar invoices from the same vendor.

Each page is presented in LINE TEXT format:
    [y=<y0>-<y1>]  <x0>-<x1>:<word>  <x0>-<x1>:<word>  ...

Every word on every page is in this format — x0/y0 is the top-left corner,
x1/y1 is the bottom-right corner of that word's bounding box in PDF points.
Use these coordinates directly to compute region_bbox.

════════════════════════ YOUR TASK ════════════════════════════════════════════

Read the SAMPLE page like a human would. Use your knowledge of how telecom invoices
are laid out to SEMANTICALLY IDENTIFY what each piece of data represents —
regardless of how the vendor labels it.

For EVERY field produce BOTH:
  1. region_bbox  — coordinates of the VALUE word(s) from the word list
  2. regex_pattern — a regex that matches the value in the full page text

This dual approach makes extraction robust: region is tried first; if it
returns empty, the extractor automatically falls back to the regex.

════════════════════════ LANGUAGE & LOCALE NOTES ════════════════════════════

The invoice may be in ANY language (English, French, Spanish, German, Arabic,
Chinese, Japanese, Portuguese, etc.) or any country locale. This does NOT change your task:
  • Map labels SEMANTICALLY regardless of the language they are written in.
  • For regex_pattern, anchor to the actual label text as it appears on the
    page (e.g. French "Numéro de compte", German "Kontonummer", Portuguese "Utilizado", etc.).
  • For currency values, write regex patterns that match both decimal formats:
    - Anglo: 1,234.56  →  use  [\\d,.]+  in the capture group
    - European: 1.234,56  →  same pattern covers both
  • For dates, match the format as printed; do not assume MM/DD/YYYY.

════════════════════════ SEMANTIC MAPPING GUIDE ══════════════════════════════

Map whatever label the vendor uses to the correct canonical field name:

  account_number       — account/customer/client ID  
  invoice_number       — invoice/bill/statement number or reference  
  invoice_date         — date bill was issued ("Issue Date", "Bill Date", etc.)  
  billing_period       — service date range ("Monthly charges Nov 01 - Nov 30")  
  due_date             — payment due date  
  customer_name        — account holder name  
  customer_address     — full billing address  
  previous_balance     — balance from last bill  
  payments_received    — payments/credits applied  
  new_charges_total    — new charges before payments  
  phone_number         — mobile/wireless number (ddd.ddd.dddd or (ddd) ddd-dddd)  
  subscriber_name      — name of the person on this line  
  plan_name            — rate plan/service package name  
  monthly_access_charge — base monthly line fee  
  voice_minutes_used   — minutes consumed ("Talk", "Voice", "Daytime minutes")
                         Look in "Used"/"Consumed" column, NOT the "Included" column
  voice_minutes_included — minutes in plan (often "unlimited" or a number)  
  data_usage_used      — data consumed. Capture the numeric value only — the
                         post-processor appends the unit (KB/MB/GB) automatically
                         by reading it from data_usage_included.
  data_usage_included  — data allowance in plan with unit (e.g. "5 GB", "3,145,728 KB")
  messages_sent        — SMS/text count used ("Text", "SMS", "Messaging")  
  messages_included    — messages in plan  
  monthly_charges_subtotal  — recurring charges subtotal  
  usage_charges_subtotal    — usage/overage subtotal  
  surcharges_subtotal       — surcharges/regulatory fees subtotal  
  taxes_and_fees_subtotal   — government taxes/fees subtotal  
  total_current_charges     — grand total for this invoice or subscriber line
                              Common labels: "Total Charges", "TOTAL", "Total",
                              "Valor", "VALOR DO VIVO", "Total Current Charges"
  amount_due           — net amount the customer must pay after applying credits
                         Common labels: "Total Due", "Amount Due", "Balance Due",
                         "Pay This Amount", "Please Pay"

════════════════════════ RULES FOR region_bbox ═══════════════════════════════

1. Find the VALUE word(s) in the LINE TEXT (NOT the label words).
   Each word appears as  <x0>-<x1>:<text>  on a line starting with [y=<y0>-<y1>].
2. Set region_bbox = [x0-2, y0-2, x1+2, y1+2] using those four coordinates.
3. For multi-word values, span from the leftmost x0 to the rightmost x1, ±2 pt pad.
4. Include the "$" word in the bbox if it is a separate word before the amount.
5. source_page_hint = 1-based page number where the value appears (from PAGE header).

════════════════════════ RULES FOR regex_pattern ════════════════════════════

Write a Python regex with EXACTLY ONE capture group that:
  • Starts with a portion of the label text so it is anchored  
  • Ends with a pattern matching the value format  
  • Uses \\s+ for spaces (the extractor joins words with spaces)  
  • Is case-insensitive  

Examples:
  account_number     → "Account\\s+Number[:\\s]+([\\d]+)"
  invoice_date       → "Issue\\s+Date[:\\s]+([A-Za-z]+\\s+\\d{1,2},?\\s+\\d{4})"
  phone_number       → "(\\d{3}[.-]\\d{3}[.-]\\d{4})"
  amount_due         → "(?:Amount|Balance)\\s+Due[:\\s]+([\\d,.]+)"
                        ← DO NOT use "\\bTOTAL" for amount_due; TOTAL maps to total_current_charges
  total_current      → "\\bTOTAL\\s+([\\d,.]+)"  — (\\b ensures whole-word, not "Subtotal")
  total per line     → "Total\\s+for\\s+[\\d.]+\\s+\\$([\\d,.]+)"
  minutes used       → "Daytime\\s+minutes\\s+\\([^)]+\\)\\s+(\\d+)"
  data used          → "Data\\s+Used.*?(?:\\d+\\s*(?:GB|MB)).*?([\\d,]+)"  — captures number only; post-processor appends unit
  
NOTE: For currency amounts, use ([\\d,.]+) to match both European (15,50) and US (15.50) formats.
      Use \\s+ (not [:\\s]+) to match whitespace between label and value.
      Use \\b before keywords like TOTAL, SUBTOTAL, AMOUNT to ensure you match the complete word.
      This prevents "TOTAL" from matching "Subtotal" or "AMOUNT" from matching "PAYMENT_AMOUNT".
      
NOTE: For data_usage_used, capture the NUMERIC VALUE ONLY — never capture the unit in the regex.
      The post-processor reads the unit from data_usage_included and appends it automatically.
      Use flexible patterns like "Data\\s+Used.*?(<plan capacity>).*?([\\d,]+)" to skip over
      plan names, service types, and other text between the label and the used value.

════════════════════════ USAGE SUMMARY EXTRACTION ═══════════════════════════

⚠️  CRITICAL: Almost EVERY individual invoice has a USAGE SUMMARY section.
   READ THE INVOICE LIKE A HUMAN and actively search for usage tables.

Most telecom invoices show consumption details in a tabular format. The layout
varies by vendor but the SEMANTIC MEANING is consistent. Your job is to:

  1. LOCATE the usage summary table/section (often labeled "Usage Summary",
     "Account Summary", "Your Usage", "Service Details", etc.)
  
  2. IDENTIFY the column that shows CONSUMED/USED amounts
     Common column headers: "Used", "Consumed", "Total", "Actual", or sometimes
     just numeric values without a clear "Used" header
  
  3. IDENTIFY rows for these service types (vendors use different labels):
     ┌─────────────────────────────────────────────────────────────────────┐
     │ Text/SMS/Messages/Messaging   →  extract as messages_sent           │
     │ Voice/Talk/Minutes/Calls       →  extract as voice_minutes_used     │
     │ Data/Internet/Mobile Data      →  extract as data_usage_used        │
     └─────────────────────────────────────────────────────────────────────┘

  4. MAP each row label to the value in the "Used" (or equivalent) column
     - Act like a human: scan left-to-right across the row
     - Find the numeric value that represents consumption
     - Ignore "Included", "Remaining", "Allowance" columns — focus on "Used"

IMPORTANT: Extract the USAGE VALUES from the "Used"/"Consumed" column:
  • For messages: Extract the numeric count (e.g., "145", "0", "328")
  • For voice: Extract minutes/duration as printed (e.g., "325 min", "Unlimited", "1,205")
  • For data: Capture the NUMERIC VALUE ONLY (e.g., "2.5", "1250", "987,212")
              The post-processor appends the unit (GB/MB/KB) from data_usage_included.

NOT ALL INVOICES HAVE ALL THREE — some may only show data, or only voice + data.
Extract whatever is present; do not invent missing fields.

SPATIAL LAYOUT VARIATIONS — usage values can appear in TWO formats:
  
  📊 HORIZONTAL (most common): Values appear to the RIGHT of row labels
     Text       Unlimited   145        —            ← usage value x0 > label x0
     Voice      500 min     325 min    175 min
     Data       5 GB        2.3 GB     2.7 GB
  
  📊 VERTICAL: Values appear BENEATH column headers
     Type        Text       Voice      Data         ← row labels
     Used        145        325 min    2.3 GB       ← usage values y0 > label y0
     Included    Unlimited  500 min    5 GB

To locate values, use word coordinates:
  • HORIZONTAL: Find label word, then scan for words with SAME y0 (±3pt) but HIGHER x0
  • VERTICAL: Find column header, then scan for words with SAME x0 (±30pt) but HIGHER y0

EXTRACTION STRATEGIES for usage values:
  1. region_bbox: Locate the value word(s) in the "Used" column by:
     - Finding the row label (e.g. "Text", "Voice", "Data")
     - Scanning horizontally (right) OR vertically (down) for the consumption value
     - Using the word coordinates (x0, y0) from the word list to determine position
  
  2. regex_pattern: Anchor to the row label and capture the usage number
     Be FLEXIBLE — the value may appear on the same line or several lines after the
     "Used" header. The column header may vary or be absent.
     
     CRITICAL FOR DATA USAGE: The used value often appears WITHOUT its unit, while
     the included amount shows the unit. Pattern strategy:
       • Start with "Data" and "Used" to establish context
       • Use .*? to skip intervening content (plan names, specs, etc.)
       • Look for numeric values near plan capacity indicators (e.g., "3GB", "5GB", "10GB")
       • Capture the number even if KB/MB/GB appears separately on another line
       • The post-processor will append the unit from data_usage_included if missing
     
     Examples:
       • Messages: "(?:Text|SMS|Messaging|Messages?)\\s+(?:.*?\\s+)?([0-9,]+)(?!.*(?:Included|Remaining))"
       • Voice: "(?:Voice|Talk|Minutes?|Calls?)\\s+(?:.*?\\s+)?([\\d,]+)\\s*(?:min|minutes)?"
       • Data (generic): "Data\\s+Used.*?(?:[\\d]+\\s*(?:GB|MB|KB)).*?([\\d,]+)"
         ↑ Matches "Data Used ... 3GB ... 987,212" or "Data Used ... 5 GB ... 2.3 GB"
       • Data (with plan): "Data.*?(?:\\d+GB|\\d+MB).*?([\\d,]+)"
         ↑ Flexible pattern that finds used value near plan capacity indicators, even if the column header is missing or unclear.

If the usage section shows "Included" amounts as well, also extract:
  • messages_included — from "Included"/"Plan"/"Allowance" column
  • voice_minutes_included  
  • data_usage_included (always capture WITH unit — e.g. "5 GB", "3,145,728 KB")

EXAMPLE table structures you might encounter:
  
  Type          Included    Used       Remaining
  Text          Unlimited   145        —
  Voice         500 min     325 min    175 min
  Data          5 GB        2.3 GB     2.7 GB
  
  OR:
  
  Service            Plan        This Month
  Messaging          Unlimited   328 messages
  Daytime minutes    Unlimited   1,205 min
  Data usage         10 GB       4.52 GB
"""

# ── Per-vendor system-prompt snippets ─────────────────────────────────────────
# Only the matching vendor block is injected at LLM call time,
# reducing token count when the vendor is already identified.
_VENDOR_PROMPT_NOTES: Dict[str, str] = {
    "vivo": """\
▶ VIVO (Brazil / Portuguese-language invoices)
  • "Utilizado" column = "Used"
  • Voice/talk row labels: "GESTAO VOZ"
    - Voice value under Utilizado Minutos/Unidades column: "06m24s" or "84m12s" capture into "voice_minutes_used" key.
  • total_current_charges: look in the "VALOR DO VIVO" summary section.
    The TOTAL row (last row, rightmost value) is the grand total.
    Example layout:
        VALOR DO VIVO 11-11111-1111
        SERVIÇOS CONTRATADOS        9,26
        SERVIÇOS TELEFÔNICA BRASIL  6,24
        TOTAL                       15,50  ← total_current_charges
    Regex: r"\\bTOTAL\\s+([\\d,.]+)"
  • amount_due: this is a DIFFERENT field — it is the net payable amount
    after credits, usually in the bill header (NOT the VALOR DO VIVO section).""",

    "telekom": """\
▶ Telekom (Germany / German-language invoices)
  • Subscriber grouping key: "Ihre Mobilfunk-Kartennummer" (e.g. "8-94902-00001-86125991-2") —
    this is a SIM card number used for page grouping, NOT the phone_number field.
  • phone_number: extract from "Rufnummer Telefonie (0151)11183612"
    Regex: r"Rufnummer\\s+Telefonie\\s+(\\(\\d{3,5}\\)\\d{6,9})"
  • data_usage_used: row label "INSGESAMT VERBRAUCHTES DATENVOLUMEN"
    Value is in KB with German dot-thousands separator (e.g. "1.018.539 KB").
    Regex (MB|KB only — do NOT capture the plan volume in GB):
    r"INSGESAMT\\s+VERBRAUCHTES\\s+DATENVOLUMEN[^\\n]*?([\\d.,]+\\s*(?:KB|MB|GB))"
  • data_usage_included: row label "VERTRAGLICH VEREINBARTES DATENVOLUMEN" — value in KB (e.g. "10.485.760 KB")
  • invoice_date: "Datum" label, format DD.MM.YY
  • invoice_number: "Rechnungsnummer" label
  • total_current_charges: "Rechnungsbetrag" or "Gesamtbetrag"
  • amount_due: "zu zahlen" """,

    "att": """\
▶ AT&T (US)
  • Usage Summary shows: "Daytime minutes", "Daytime minutes (unlimited)", "Night & Weekend minutes",
    "Mobile to Mobile minutes", "Messaging", "Data", "UNL DOM Messaging (unlimited)" for Text/messages.
  • Pool usage lines: "w/VVM (unlimited) NNN" — NNN is the used count.
  • Per-subscriber total: "Total for NNN.NNN.NNNN  $NN.NN"
    Regex: r"Total\\s+for\\s+[\\d.]+\\s+\\$([\\d,.]+)"  → total_current_charges""",

    "verizon": """\
▶ Verizon (US)
  • Usage detail columns: "Allowance", "Used", "Billed"
  • Voice/data/messaging rows end with "--" or "-" as separator before billed column.
  • Per-subscriber total footer: "Total Current Charges for NNN-NNN-NNNN  $NN.NN"
    The phone number is embedded in the label — use a permissive regex:
    r"Total\\s+Current\\s+Charges\\s+for\\s+[\\d\\-]+\\s+\\$([\\d,]+(?:\\.\\d+)?)"  → total_current_charges
  • Sections: "Surcharges and Other Charges" → surcharges_subtotal
               "Taxes, Governmental Surcharges and Fees" → taxes_and_fees_subtotal""",
}

_SYSTEM_PROMPT_SUFFIX = """
════════════════════════ WHAT TO INCLUDE ═════════════════════════════════════

• Include a rule for EVERY canonical field whose value is clearly visible.
• Do NOT skip visible fields. Do NOT invent fields not present.
• Distinguish total_current_charges (grand total of charges) from amount_due
  (net payable after credits). Both may appear; extract each if visible.
• ALWAYS look for and extract usage summary values (messages, voice, data)
  from the "Used" column if a usage section is present.
• For call/data detail tables, populate the line_items section.

════════════════════════ OUTPUT SCHEMA ══════════════════════════════════════

Return ONLY valid JSON — no markdown fences, no explanation.

{
  "meta": {
    "document_type": "<invoice | bill | statement>",
    "vendor_hint":   "<vendor name if visible, else null>",
    "sample_pages":  [<1-based page numbers>],
    "page_width_pt": <width>,
    "page_height_pt":<height>
  },
  "fields": [
    {
      "field_name":         "<canonical snake_case from the mapping guide>",
      "description":        "<what this value represents>",
      "strategy":           "regex",
      "source_page_hint":   <1-based page number>,
      "anchor_text":        null,
      "anchor_tolerance_x": 5,
      "anchor_tolerance_y": 5,
      "max_distance":       200,
      "value_offset_x":     null,
      "value_offset_y":     null,
      "region_bbox":        [x0-2, y0-2, x1+2, y1+2],
      "regex_pattern":      "<Python regex with ONE capture group, or null>",
      "table_row":          null,
      "table_col":          null,
      "value_type":         "<string|date|currency|integer|float>",
      "required":           <true|false>
    }
  ],
  "line_items": {
    "enabled":              <true|false>,
    "header_anchor_text":   "<first word of header row or null>",
    "header_y_tolerance":   <pt>,
    "stop_anchor_text":     "<word ending the table or null>",
    "source_page_hint":     <1-based page or null>,
    "columns": [
      {
        "field_name":  "<snake_case>",
        "header_text": "<column header as printed>",
        "x_center":    <column centre pt>,
        "x_tolerance": <±pt, default 40>,
        "value_type":  "<string|date|currency|integer|float>"
      }
    ]
  }
}
"""


def _build_system_prompt(vendor: Optional[str] = None) -> str:
    """
    Assemble the LLM system prompt, injecting only the relevant vendor notes.

    When ``vendor`` is known and present in ``_VENDOR_PROMPT_NOTES``, only that
    vendor's block is included — reducing the prompt token count significantly.
    Falls back to all vendor blocks when the vendor is None or unrecognised.
    """
    vendor_key = _resolve_vendor_key(vendor) if vendor else None
    header = (
        "\n════════════════════ VENDOR-SPECIFIC NOTES ══════════════════════════════════\n\n"
        "Apply these rules ONLY when the invoice belongs to that vendor.\n\n"
    )
    if vendor_key and vendor_key in _VENDOR_PROMPT_NOTES:
        notes = _VENDOR_PROMPT_NOTES[vendor_key]
        logger.debug(
            f"_build_system_prompt: injecting vendor-specific notes for '{vendor_key}'"
        )
    else:
        notes = "\n\n".join(_VENDOR_PROMPT_NOTES.values())
        logger.debug(
            "_build_system_prompt: injecting all vendor notes "
            "(vendor unknown or not in registry)"
        )
    return _SYSTEM_PROMPT_BASE.strip() + "\n\n" + header + notes + "\n" + _SYSTEM_PROMPT_SUFFIX.strip() + "\n"


def generate_rules_via_llm(layout_data: Dict, deployment: Optional[str] = None, vendor: Optional[str] = None) -> Dict:
    """
    Generate extraction rules using Azure OpenAI (UNKNOWN LAYOUT path).
    
    Builds two representations of the page data and sends them together:
      1. Compact JSON word list  — exact coordinates for bbox lookup.
      2. LINE TEXT visual layout — spatial layout the LLM reads like a human.

    The LLM is instructed (via SYSTEM_PROMPT) to semantically map vendor labels
    to canonical field names and output both a regex_pattern and a region_bbox
    for every visible field.

    Retries up to 5 times with exponential backoff (5→10→20→40s) on failure.
    Strips markdown fences and leading non-JSON text from the response before
    parsing. Raises ValueError if the response is empty or not valid JSON.
    """
    logger.info("→ Using LLM SCHEMA GENERATOR (unknown layout)")
    
    client = _get_openai_client()
    deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_GPT5", "gpt-5")

    pages_data = layout_data["pages"]
    all_words  = layout_data["all_words"]

    # LINE TEXT embeds x0, y0, x1, y1 per word (format: [y=y0-y1] x0-x1:word).
    # This gives the LLM everything needed to write region_bbox values for any
    # page without a separate JSON word list — cutting input tokens by ~70%.
    visual = build_line_text(pages_data)

    user_message = (
        f"SAMPLE INVOICE: {len(pages_data)} page(s) — pages {[pg['page_num'] for pg in pages_data]}\n"
        f"Generate extraction rules that will work on thousands of similar invoices from this vendor.\n\n"
        f"LINE TEXT — all {len(pages_data)} page(s):\n"
        + "Format: [y=<y0>-<y1>]  <x0>-<x1>:<word>  ...\n"
        + "• x0/y0 = top-left, x1/y1 = bottom-right (PDF points) — use for region_bbox\n"
        + "• Words on same y (±3pt) = same row (horizontal table)\n"
        + f"• Words on same x (±30pt) = same column (vertical table)\n\n{visual}"
    )

    est_chars  = len(user_message)
    est_tokens = est_chars // 4
    # Use 'medium' reasoning effort for large prompts (>10k tokens) to reduce
    # hallucination risk on complex multi-page layouts; 'low' otherwise for speed.
    _reasoning = "medium" if est_tokens > 10_000 else "low"
    logger.info(
        f"Sending {len(all_words)} total words across "
        f"{len(pages_data)} page(s) to Azure OpenAI ({deployment}) "
        f"[~{est_chars} chars / ~{est_tokens} tokens input]  reasoning_effort={_reasoning}…"
    )

    max_retries = 5
    base_delay  = 5  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            raw_chunks = []
            finish_reason = None
            with client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": _build_system_prompt(vendor).strip()},
                    {"role": "user",   "content": user_message},
                ],
                max_completion_tokens=16000,
                reasoning_effort=_reasoning,  # 'medium' for large prompts, 'low' otherwise
                seed=42,
                stream=True,
            ) as stream:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.delta.content:
                        raw_chunks.append(choice.delta.content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            raw = "".join(raw_chunks).strip()
            if finish_reason == "length":
                logger.warning(
                    "LLM output was truncated (finish_reason=length). "
                    "Will attempt JSON auto-repair. Consider using fewer pages."
                )
            break  # success — exit retry loop
        except Exception as exc:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))   # 5, 10, 20, 40 s
            logger.warning(
                f"Request failed (attempt {attempt}/{max_retries}): {exc}. "
                f"Retrying in {delay}s…"
            )
            time.sleep(delay)
    
    logger.debug(f"Raw LLM response (first 500 chars):\n{raw[:500]}")

    if not raw:
        raise ValueError(
            "LLM returned an empty response. "
            "The model may have refused the request or max_completion_tokens "
            "was reached before any output was produced. "
            "Check the prompt length and try again."
        )

    # Strip markdown fences if model added them
    if raw.startswith("```"):
        raw = re.sub(r"^```[json]*\n?", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\n?```\s*$",     "", raw)
        raw = raw.strip()

    # Find the outermost JSON object in case the model prepended text
    first_brace = raw.find("{")
    if first_brace > 0:
        logger.warning(
            f"Model prepended {first_brace} non-JSON chars — stripping them."
        )
        raw = raw[first_brace:]

    if not raw:
        raise ValueError("No JSON object found in LLM response after cleanup.")

    try:
        rules = json.loads(raw)
        logger.info(f"✓ LLM generated rules with {len(rules.get('fields', []))} fields")
        return rules
    except json.JSONDecodeError as exc:
        logger.error(f"JSON parse failed at position {exc.pos}. Raw content:\n{raw[:2000]}")
        # ── Auto-repair: response was likely truncated mid-field ─────────────
        repaired = _attempt_json_repair(raw)
        if repaired:
            logger.warning(
                "JSON auto-repair succeeded — truncated trailing content dropped. "
                "Consider using fewer pages for complete rules."
            )
            logger.info(f"✓ LLM generated rules with {len(repaired.get('fields', []))} fields (after repair)")
            return repaired
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc



def save_rules(rules: Dict, rule_file: str, sample_pages: List[int]) -> None:
    """Persist rule dict via the active rule store backend."""
    _get_rule_store().save(rule_file, rules, sample_pages)
    logger.info(f"✓ Rules saved → {rule_file}")


# ═══════════════════════════════════════════════════════════════════════════
#                      5. OUTPUT GENERATOR (Structured Data)
# ═══════════════════════════════════════════════════════════════════════════

def save_structured_output(
    record: Dict,
    pdf_path: str,
    page_indices: List[int],
    rule_file: str,
    output_dir: Path = OUTPUT_DIR,
    user_tag: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Save extraction results to CSV and JSON files.

    If user_tag is provided (e.g. a normalised phone number from range
    processing), the output files are named after the subscriber rather
    than the page numbers, which is far more readable.

    Returns (csv_path, json_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = Path(pdf_path).stem

    if user_tag:
        # Sanitise tag so it is safe as a filename component
        safe_tag = re.sub(r"[^\w\-]", "_", user_tag)
        csv_path  = output_dir / f"{base_name}_user_{safe_tag}_{timestamp}.csv"
        json_path = output_dir / f"{base_name}_user_{safe_tag}_{timestamp}.json"
    else:
        pages_tag = "_".join(str(idx + 1) for idx in page_indices)
        csv_path  = output_dir / f"{base_name}_pages_{pages_tag}_{timestamp}.csv"
        json_path = output_dir / f"{base_name}_pages_{pages_tag}_{timestamp}.json"
    
    # CSV - flat fields only
    flat = {k: v for k, v in record.items() if not k.startswith("_")}
    flat["_source_pages"] = str([idx + 1 for idx in page_indices])
    flat["_line_item_count"] = record.get("_line_item_count", 0)
    flat["source_pdf"] = Path(pdf_path).name
    flat["extraction_date"] = datetime.now().isoformat()
    flat["rule_file"] = Path(rule_file).name
    
    df = pd.DataFrame([flat])
    df.to_csv(csv_path, index=False)
    logger.info(f"✓ CSV saved → {csv_path}")
    
    # JSON - full record including line items
    record["_metadata"] = {
        "source_pdf": Path(pdf_path).name,
        "source_pages": [idx + 1 for idx in page_indices],
        "rule_file": Path(rule_file).name,
        "extraction_date": datetime.now().isoformat(),
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"✓ JSON saved → {json_path}")
    
    return str(csv_path), str(json_path)


# ═══════════════════════════════════════════════════════════════════════════
#                         MAIN PROCESSING FLOW
# ═══════════════════════════════════════════════════════════════════════════

def process_invoice(
    pdf_path: str,
    page_indices: List[int],
    force_generate: bool = False,
    similarity_threshold: float = 0.9,
    deployment: Optional[str] = None,
    user_tag: Optional[str] = None,
    precomputed_layout: Optional[Dict] = None,
    save_files: bool = True,
    vendor: Optional[str] = None,
) -> Dict:
    """
    Main invoice processing pipeline following the smart routing architecture.
    
    Flow:
      1. Extract layout data (PDF → words)
      2. Generate fingerprint
      3. Match against known formats
      4. If known → extract with rules
      5. If unknown → generate rules via LLM, save fingerprint, then extract
      6. Save structured output
    
    Returns dict with extraction results and metadata.
    """
    pdf_path = str(pdf_path)
    pages_str = ", ".join(str(i+1) for i in page_indices)
    
    logger.info("="*70)
    logger.info(f"PROCESSING: {Path(pdf_path).name} (pages: {pages_str})")
    logger.info("="*70)
    
    # STEP 1: Layout Extraction
    logger.info("\n[1/5] LAYOUT EXTRACTION")
    if precomputed_layout is not None:
        layout_data = precomputed_layout
        logger.info(
            f"✓ Using cached layout: {len(layout_data['all_words'])} words "
            f"from {len(page_indices)} page(s) (no PDF re-open)"
        )
    else:
        layout_data = extract_layout_data(pdf_path, page_indices)
        logger.info(f"✓ Extracted {len(layout_data['all_words'])} words from {len(page_indices)} page(s)")
    
    # STEP 2: Fingerprint Generation
    logger.info("\n[2/5] FINGERPRINT GENERATION")
    fingerprint = generate_fingerprint(layout_data)
    logger.info(f"✓ Fingerprint: {fingerprint['hash']}")
    
    # STEP 3: Format Matching
    logger.info("\n[3/5] FORMAT MATCHING")
    matched_format = None if force_generate else match_fingerprint(fingerprint, similarity_threshold, vendor=vendor)
    
    # STEP 4: Extraction Strategy
    logger.info("\n[4/5] DATA EXTRACTION")
    
    if matched_format:
        # KNOWN LAYOUT → Rule-based extraction
        # Vendor precedence:
        #   1. CLI arg (most trusted)
        #   2. Current page fingerprint vendor_hint (freshly detected)
        #   3. Stored fingerprint vendor_hint (may be stale/None)
        _hint = matched_format.get("fingerprint", {}).get("vendor_hint") or vendor
        rule_file = matched_format["rule_file"]
        if not _get_rule_store().exists(rule_file, vendor=_hint):
            logger.warning(f"Rule file not found: {rule_file}, falling back to LLM generation")
            matched_format = None
    
    if matched_format:
        # Known layout path
        record = extract_with_rules(layout_data, rule_file, vendor=_hint)
        rule_file = matched_format["rule_file"]
        
    else:
        # UNKNOWN LAYOUT → LLM Schema Generation
        rules = generate_rules_via_llm(layout_data, deployment)

        # Vendor precedence: CLI arg → fingerprint auto-detect → fallback
        effective_vendor = vendor or fingerprint.get("vendor_hint") or "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rule_filename = f"rule_{effective_vendor}_{timestamp}.json"
        # Relative key  e.g. "verizon/rule_verizon_20260302_213712.json"
        # The rule store creates the vendor subfolder (local) or blob path (azure).
        rule_file = f"{effective_vendor}/{rule_filename}"

        save_rules(rules, rule_file, [i+1 for i in page_indices])

        # Save fingerprint
        save_fingerprint(
            fingerprint,
            name=f"{effective_vendor}_{timestamp}",
            rule_file=rule_file,
            sample_pages=[i+1 for i in page_indices],
            vendor=effective_vendor,
        )
        
        # Extract with newly generated rules
        record = extract_with_rules(layout_data, rule_file, vendor=effective_vendor)

    # Apply default "0" / "0 MB" for missing usage fields and normalise types
    record = _apply_usage_defaults(record)

    # STEP 5: Output Generation
    logger.info("\n[5/5] STRUCTURED OUTPUT")
    if save_files:
        csv_path, json_path = save_structured_output(
            record, pdf_path, page_indices, rule_file, user_tag=user_tag
        )
    else:
        csv_path, json_path = "", ""
        logger.info("  (skipping individual files — consolidated CSV only)")
    
    logger.info("\n" + "="*70)
    logger.info("✓ PROCESSING COMPLETE")
    logger.info("="*70)
    
    return {
        "success": True,
        "csv_path": csv_path,
        "json_path": json_path,
        "record": record,
        "fingerprint_hash": fingerprint["hash"],
        "was_known_format": matched_format is not None,
        "rule_file": rule_file,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
#          6. USER-SECTION GROUPING  (Select pages belonging to the same subscriber)
# ══════════════════════════════════════════════════════════════════════════════════════

# ── Compiled patterns used by the fast-scan phase ────────────────────────────

# Matches phone/line identifiers across multiple regional formats:
#
#   North American  :  XXX.XXX.XXXX | (XXX) XXX-XXXX | XXX-XXX-XXXX
#   Brazilian (VIVO):  DD-DDDDD-DDDD  e.g. 11-91249-1684  (no parentheses)
#   Brazilian (local):  (DD) 9XXXX-XXXX  e.g. (11) 98765-4321
_PHONE_RE = re.compile(
    r''
    # ── North American: (XXX) XXX-XXXX / XXX.XXX.XXXX / XXX-XXX-XXXX ────
    r'(?:\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4})'
    # ── Brazilian no-parentheses: DD-DDDD-DDDD or DD-DDDDD-DDDD ────────
    # Matches VIVO format "11-91249-1684" as it appears in
    # "VEJA O USO DETALHADO DO VIVO 11-91249-1684"
    r'|(?:(?<![\d/])\d{2}-\d{4,5}-\d{4}(?![\d]))'
    # ── Brazilian with parentheses: (DD) 9XXXX-XXXX ──────────────────
    r'|(?:\(\d{2}\)\s*\d{4,5}[\-]\d{4})'
    # ── Telekom (Germany) Mobilfunk-Kartennummer: 8-NNNNN-NNNNN-NNNNNNNN-N ─
    # Used as the per-subscriber grouping key on Telekom invoices.
    # Example: "8-94902-00001-86125991-2"
    r'|(?:(?<!\d)8-\d{5}-\d{5}-\d{8}-\d(?!\d))'
)

# Billing-total keywords that signal the LAST page of a subscriber's section.
# Covers English (Verizon, AT&T) and Portuguese (VIVO, Claro, TIM, Oi).
_TOTAL_RE = re.compile(
    r'\b('
    # ── English ──────────────────────────────────────────────────────────
    r'total\s+current\s+charges?'
    r'|total\s+charges?'
    r'|amount\s+due'
    r'|balance\s+due'
    r'|pay\s+this\s+amount'
    r'|total\s+due'
    r'|total\s+amount\s+due'
    # ── Portuguese / VIVO ──────────────────────────────────────────────
    r'|valor\s+do\s+vivo'       # VIVO: "VALOR DO VIVO 11-91249-1684"
                                # (subscriber billing-summary header —
                                #  always on the last page of each line section)
    r'|total\s+a\s+pagar'       # generic: "Total a Pagar"
    r'|valor\s+total\s+da\s+fatura'
    r'|total\s+da\s+fatura'
    r'|total\s+geral'
    r'|valor\s+a\s+pagar'
    # ── German / Telekom ──────────────────────────────────────────────
    r'|rechnungsbetrag'          # Telekom: invoice total amount
    r'|gesamtbetrag'             # generic German: grand total
    r'|zu\s+zahlen'              # "zu zahlen" = amount to pay
    r')\b',
    re.IGNORECASE,
)


def _normalize_phone(phone: str) -> str:
    """Reduce a phone string to digits only for reliable equality comparison."""
    return re.sub(r'\D', '', phone)


def _build_layout_data(page_data_list: List[Dict]) -> Dict:
    """
    Assemble a standard layout_data dict (same structure as
    extract_layout_data returns) from a list of per-page dicts that are
    already held in memory.  No PDF I/O.

    Each item in page_data_list must have:
        page_num, width, height, words, text, tables
    """
    result: Dict = {
        "pages":     [],
        "all_words": [],
        "full_text": [],
        "tables":    [],
    }
    for p in page_data_list:
        result["pages"].append({
            "page_num": p["page_num"],
            "width":    p["width"],
            "height":   p["height"],
            "words":    p["words"],
        })
        result["all_words"].extend(p["words"])
        result["full_text"].append(p["text"])
        result["tables"].extend(p["tables"])
    return result


def process_invoice_range(
    pdf_path: str,
    end_page: int,
    force_generate: bool = False,
    similarity_threshold: float = 0.9,
    deployment: Optional[str] = None,
    vendor: Optional[str] = None,
    pdf_obj: Optional[Any] = None,
    session_id: Optional[str] = None,
) -> "tuple[List[Dict], Optional[str]]":

    """
    Streaming range-based invoice processing pipeline.

    The PDF is opened exactly once.  Pages are read one at a time; each
    user section is extracted and written to disk IMMEDIATELY when it is
    complete — the moment a billing-total keyword or a phone-number change
    is detected.  Only the pages belonging to the currently open group are
    held in memory at any given moment.

    A group is considered complete (and flushed) when:
      • Current page has the group's phone  AND  a billing-total keyword.
      • Current page has a DIFFERENT phone  (previous group flushed first).
      • Current page has NO phone at all    (previous group flushed, page
        discarded as a summary / garbage page).
      • End of range is reached             (any open group is flushed).

    Post-total same-phone pages are silently skipped.

    Parameters
    ──────────
    pdf_path            : path to the PDF file
    end_page            : last  page to scan (1-based, inclusive)
    force_generate      : skip fingerprint matching, always call LLM
    similarity_threshold: fingerprint match threshold (default 0.9)
    deployment          : Azure OpenAI deployment override
    vendor              : carrier name (e.g. "vivo", "att") — scopes fingerprint
                          matching and is used as the prefix in rule file names
    pdf_obj             : an already-open pdfplumber.PDF instance. When provided
                          the function skips its internal pdfplumber.open() call
                          (avoids double-open when the caller already holds the
                          file handle). The caller retains ownership and is
                          responsible for closing the PDF.

    Returns
    ───────
    (results, consolidated_csv_path)

    results               – List of result dicts (one per user group).
    consolidated_csv_path – Path to the merged CSV, or None if no successes.
    """
    pdf_path     = str(pdf_path)
    page_indices = list(range(0, end_page))   # 0-based, always from page 1

    logger.info("=" * 70)
    logger.info(
        f"RANGE PROCESSING (streaming): {Path(pdf_path).name}  "
        f"pages 1–{end_page}  ({len(page_indices)} pages)"
    )
    logger.info("=" * 70)

    # ── Mutable state ─────────────────────────────────────────────────────────
    # current_group carries BOTH metadata AND the raw page data for the
    # subscriber being accumulated.  Once flushed, it is set to None so
    # Python can garbage-collect those pages immediately.
    current_group: Optional[Dict] = None   # {phone, phone_norm, page_indices, page_data}
    closed_phones: set            = set()  # phone_norms whose billing total was seen
    results:       List[Dict]     = []
    group_counter: int            = 0
    _last_heartbeat:   float      = time.time()
    _heartbeat_interval: int      = 60     # seconds

    # ── Grouping column name ──────────────────────────────────────────────────
    # Different carriers print different identifiers in the per-subscriber
    # section header of their PDF invoices:
    #
    #   Telekom  → Mobilfunk-Kartennummer (a 20-digit SIM card account number,
    #               NOT a dialable phone number / MSISDN).  Storing this under a
    #               column called 'phone' would be misleading and would silently
    #               break any downstream step that assumes the column contains a
    #               callable E.164 number.  → column name = 'subscriber_id'
    #
    #   All other vendors (Vivo, AT&T, etc.) → actual MSISDN / phone number
    #               → column name = 'phone'
    #
    # _resolve_vendor_key normalises the caller-supplied vendor string (handles
    # capitalisation differences, whitespace, and common aliases) before the
    # comparison so callers do not have to pass an exact case-sensitive string.
    _resolved_vendor = _resolve_vendor_key(vendor)
    _grouping_col    = "phone"  # always 'phone'; for Telekom the actual phone number is in 'phone_number'

    def _flush(group: Dict, reason: str) -> Dict:
        """Assemble layout_data from the in-memory group and process it now."""
        nonlocal group_counter
        group_counter += 1
        pages_human = [p + 1 for p in group["page_indices"]]
        logger.info(
            f"\n{'─' * 70}\n"
            f"PROCESSING GROUP {group_counter}: {group['phone']}  "
            f"(pages {pages_human})  [{reason}]\n"
            f"{'─' * 70}"
        )
        layout_data = _build_layout_data(group["page_data"])
        try:
            result = process_invoice(
                pdf_path=pdf_path,
                page_indices=group["page_indices"],
                force_generate=force_generate,
                similarity_threshold=similarity_threshold,
                deployment=deployment,
                user_tag=group["phone_norm"],
                precomputed_layout=layout_data,
                save_files=False,
                vendor=vendor,
            )
            # Store the raw grouping key (Kartennummer or phone) under the
            # vendor-appropriate column name determined above.
            result[_grouping_col] = group["phone"]
            result["source_pages"] = pages_human
            return result
        except Exception as exc:
            logger.error(
                f"Failed to process group for {group['phone']} "
                f"(pages {pages_human}): {exc}"
            )
            return {
                "success":       False,
                _grouping_col:   group["phone"],
                "source_pages":  pages_human,
                "error":         str(exc),
            }

    # ── Streaming CSV setup (written incrementally — one row per subscriber) ──
    _csv_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _pdf_stem      = Path(pdf_path).stem
    out_csv_path   = OUTPUT_DIR / f"{_pdf_stem}_range_1_{end_page}_{_csv_timestamp}.csv"
    _csv_fh        = None   # opened lazily on the first successful result
    _csv_writer    = None
    _csv_rows: int = 0

    def _append_to_csv(result: Dict) -> None:
        nonlocal _csv_fh, _csv_writer, _csv_rows
        if not result.get("success") or not result.get("record"):
            return
        record      = result["record"]
        data_fields = [k for k in record if not k.startswith("_")]
        row = {
            _grouping_col:  result.get(_grouping_col, ""),
            "source_pages": ", ".join(str(p) for p in result.get("source_pages", [])),
        }
        row.update({k: record[k] for k in data_fields})
        if _csv_writer is None:
            fieldnames  = [_grouping_col, "source_pages"] + data_fields
            _csv_fh     = open(out_csv_path, "w", newline="", encoding="utf-8")
            _csv_writer = csv.DictWriter(_csv_fh, fieldnames=fieldnames, extrasaction="ignore")
            _csv_writer.writeheader()
        _csv_writer.writerow(row)
        _csv_fh.flush()
        _csv_rows += 1
        logger.info(f"  ✓ Row {_csv_rows} appended to CSV → {out_csv_path.name}")

    # ── Single PDF open — streaming page-by-page ──────────────────────────────
    # Use an already-open PDF object when the caller provides one (avoids a
    # second pdfplumber.open on the same file).  contextlib.nullcontext wraps
    # the existing object so the `with` block never closes it.
    _pdf_ctx = contextlib.nullcontext(pdf_obj) if pdf_obj is not None else pdfplumber.open(pdf_path)
    with _pdf_ctx as pdf:
        total_pdf_pages = len(pdf.pages)

        for idx in page_indices:
            if idx >= total_pdf_pages:
                logger.warning(
                    f"  Page index {idx} (page {idx + 1}) is out of range "
                    f"(PDF has {total_pdf_pages} pages) — skipping"
                )
                continue

            # ── Extract this single page ──────────────────────────────────
            page = pdf.pages[idx]

            # Cheap text-only scan FIRST — bulk-table check before any
            # expensive word/table extraction (saves up to 500 MB per page).
            text = page.extract_text() or ""

            # ── Bulk-table detection (early exit) ─────────────────────────
            # If more than one DISTINCT phone appears this page is a summary
            # table — skip without running extract_words_from_page or
            # extract_tables.  Release the pdfminer LTPage object immediately.
            distinct_phones_on_page = {
                _normalize_phone(m.group(0).strip())
                for m in _PHONE_RE.finditer(text)
            }
            if len(distinct_phones_on_page) > 1:
                # Allow the page through if it belongs to the currently open
                # group: VIVO (and some other vendors) print a per-subscriber
                # summary page that "mentions" a handful of other numbers
                # (forwarding targets, called numbers, etc.) — these must NOT
                # be skipped.  Real bulk/summary tables have dozens of phones;
                # individual pages that bleed in a few extra numbers never
                # exceed ~10 distinct values.
                belongs_to_group = (
                    current_group is not None
                    and current_group["phone_norm"] in distinct_phones_on_page
                    and len(distinct_phones_on_page) <= 10
                )
                if not belongs_to_group:
                    logger.info(
                        f"  Page {idx + 1:>5}: BULK TABLE "
                        f"({len(distinct_phones_on_page)} distinct phones detected) "
                        f"— skipping (words/tables NOT extracted)"
                    )
                    try:
                        page._layout = None   # release pdfminer LTPage cache
                    except Exception:
                        pass
                    del page
                    continue
                logger.info(
                    f"  Page {idx + 1:>5}: multi-phone ({len(distinct_phones_on_page)} detected) "
                    f"but belongs to current group {current_group['phone']} — including"
                )

            # ── Full extraction for non-bulk pages only ────────────────────
            words  = extract_words_from_page(page)
            for w in words:
                w["page_num"] = idx + 1
            tables = page.extract_tables() or []

            page_dict = {
                "page_num": idx + 1,
                "width":    round(float(page.width),  2),
                "height":   round(float(page.height), 2),
                "words":    words,
                "text":     text,
                "tables":   tables,
            }

            # Release pdfminer parsed layout now that words/tables are captured
            try:
                page._layout = None
            except Exception:
                pass
            del page

            # Periodic GC every 100 pages to reclaim pdfminer objects
            if (idx + 1) % 100 == 0:
                gc.collect()
            
            # Periodic heartbeat to prevent container timeout during long processing
            # Updates job status every 60 seconds to show the container is alive
            _now = time.time()
            if _now - _last_heartbeat >= _heartbeat_interval:
                if session_id:
                    try:
                        update_job_status(
                            session_id,
                            status="PROCESSING",
                            current_phase="PHASE_1_PROCESSING",
                            phase_message=f"Processing page {idx + 1}/{end_page} - {len(results)} sections complete"
                        )
                        logger.debug(f"  Heartbeat: page {idx + 1}/{end_page}, {len(results)} sections")
                    except Exception as hb_err:
                        logger.debug(f"  Heartbeat update failed: {hb_err}")
                _last_heartbeat = _now

            # ── Signals ───────────────────────────────────────────────────
            phone_match = _PHONE_RE.search(text)
            phone_raw   = phone_match.group(0).strip() if phone_match else None
            phone_norm  = _normalize_phone(phone_raw)  if phone_raw  else None
            has_total   = bool(_TOTAL_RE.search(text))

            logger.info(
                f"  Page {idx + 1:>5}: "
                f"phone={phone_raw or 'NONE':<16}  "
                f"has_total={has_total}"
            )

            # ── CASE 1: No phone → flush open group, discard this page ────
            if phone_norm is None:
                if current_group is not None:
                    logger.info(
                        f"  → No phone on page {idx + 1}; "
                        f"flushing group for {current_group['phone']}"
                    )
                    _r = _flush(current_group, "no-phone boundary")
                    _append_to_csv(_r)   # write full record to CSV immediately
                    results.append({     # keep only lightweight status in memory
                        "success":        _r.get("success"),
                        _grouping_col:    _r.get(_grouping_col),  # always 'phone'
                        "source_pages":   _r.get("source_pages"),
                        "error":          _r.get("error"),
                    })
                    del _r               # full record (with record dict) now GC-eligible
                    current_group = None
                else:
                    logger.debug(
                        f"  Page {idx + 1}: no phone, no open group — discarded"
                    )
                continue

            # ── CASE 2: Post-total same-phone page → skip ─────────────────
            if phone_norm in closed_phones:
                logger.debug(
                    f"  Page {idx + 1}: {phone_raw} already closed — "
                    f"skipping post-total page"
                )
                continue

            # ── CASE 3: Different phone → flush current group first ────────
            if current_group is not None and phone_norm != current_group["phone_norm"]:
                logger.info(
                    f"  → Phone changed to {phone_raw}; "
                    f"flushing group for {current_group['phone']} "
                    f"({len(current_group['page_indices'])} page(s))"
                )
                _r = _flush(current_group, "phone change")
                _append_to_csv(_r)   # write full record to CSV immediately
                results.append({     # keep only lightweight status in memory
                    "success":        _r.get("success"),
                    _grouping_col:    _r.get(_grouping_col),  # always 'phone'
                    "source_pages":   _r.get("source_pages"),
                    "error":          _r.get("error"),
                })
                del _r               # full record (with record dict) now GC-eligible
                current_group = None

            # ── Open or extend group ──────────────────────────────────────
            if current_group is None:
                current_group = {
                    "phone":        phone_raw,
                    "phone_norm":   phone_norm,
                    "page_indices": [idx],
                    "page_data":    [page_dict],
                }
            else:
                current_group["page_indices"].append(idx)
                current_group["page_data"].append(page_dict)

            # ── CASE 4: Billing total → flush immediately, free memory ────
            if has_total:
                logger.info(
                    f"  → Total found on page {idx + 1}; "
                    f"flushing group for {current_group['phone']} "
                    f"({len(current_group['page_indices'])} page(s))"
                )
                _r = _flush(current_group, "billing total")
                _append_to_csv(_r)   # write full record to CSV immediately
                results.append({     # keep only lightweight status in memory
                    "success":        _r.get("success"),
                    _grouping_col:    _r.get(_grouping_col),  # always 'phone'
                    "source_pages":   _r.get("source_pages"),
                    "error":          _r.get("error"),
                })
                del _r               # full record (with record dict) now GC-eligible
                closed_phones.add(phone_norm)
                current_group = None   # pages freed from memory immediately

    # ── End of range: flush any still-open group ──────────────────────────────
    if current_group is not None:
        logger.info(
            f"  → End of range: flushing open group for "
            f"{current_group['phone']} "
            f"({len(current_group['page_indices'])} page(s))"
        )
        _r = _flush(current_group, "end of range")
        _append_to_csv(_r)   # write full record to CSV immediately
        results.append({     # keep only lightweight status in memory
            "success":        _r.get("success"),
            _grouping_col:    _r.get(_grouping_col),  # always 'phone'
            "source_pages":   _r.get("source_pages"),
            "error":          _r.get("error"),
        })
        del _r               # full record (with record dict) now GC-eligible

    # ── Close the streaming CSV ───────────────────────────────────────────────
    if _csv_fh is not None:
        _csv_fh.close()

    if not results:
        logger.warning("No user sections found in the specified page range.")
        return [], None

    consolidated_csv = str(out_csv_path) if _csv_rows > 0 else None

    n_ok  = sum(1 for r in results if r.get("success"))
    n_err = len(results) - n_ok
    logger.info("\n" + "=" * 70)
    logger.info(
        f"RANGE PROCESSING COMPLETE — "
        f"{n_ok} succeeded, {n_err} failed "
        f"(out of {len(results)} user section(s))"
    )
    if consolidated_csv:
        logger.info(f"Consolidated CSV ({_csv_rows} row(s)): {consolidated_csv}")
    logger.info("=" * 70)

    return results, consolidated_csv


# ═══════════════════════════════════════════════════════════════════════════
#          7. AGENT TOOL ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
#
# This is the main entry point for the agent to call when it needs to extract
#   • Accepts `vendor` and `country` forwarded from the UI selections.
#   • Uses the smart-routing pipeline (fingerprint → rule-based / LLM) instead
#     of the simple regex-only pdfplumber extractor.
#   • Each PDF is processed via process_invoice_range (full-page range),
#     producing a per-subscriber-section consolidated CSV that is then stored
#     into the shared SQLite session cache — exactly as the old tool did.
#   • Returns the identical JSON envelope that Phase 1 of config.yaml expects.
# ───────────────────────────────────────────────────────────────────────────

def _load_agenticai_helpers():
    """
    Lazy-import agenticai session helpers so that invoice_processor.py remains
    usable as a standalone CLI script even without the SDK installed.
    """
    from agenticai.a2a.context import get_current_session_id
    from agenticai.tools.examples.sql_dataframe_tools import _store_dataframe
    from agenticai.tools.registry import tool_registry
    from .table_utils import drop_table_if_exists, generate_invoice_table_name
    return get_current_session_id, _store_dataframe, tool_registry, drop_table_if_exists, generate_invoice_table_name


# ── Lazy-register as soon as the module is imported by the agent ─────────────
try:
    (
        _get_session_id,
        _store_df,
        _tool_registry,
        _drop_table,
        _gen_table_name,
    ) = _load_agenticai_helpers()

    from typing import Annotated, Optional as _Opt
    from pydantic import Field as _Field

    @_tool_registry.register(
        name="invoice_pdf_to_tables",
        description=(
            "Extract structured invoice data from one or more PDF files using the smart "
            "routing pipeline (fingerprint engine → rule-based extractor for known vendors, "
            "LLM schema generator for unknown layouts). Accepts the vendor name and country "
            "received from the UI to scope fingerprint matching and LLM rule generation. "
            "Results are stored in the shared session SQLite cache and an aggregated JSON "
            "summary is returned."
        ),
        tags=["pdf", "invoice", "data-extraction", "msisdn"],
        requires_context=False,
    )
    def invoice_pdf_to_tables(
        file_paths: Annotated[
            _Opt[List[str]],
            _Field(
                default=None,
                description=(
                    "List of absolute PDF paths or file:// URIs. "
                    "Pass all PDFs in a single call for parallel processing."
                ),
            ),
        ] = None,
        vendor: Annotated[
            _Opt[str],
            _Field(
                default=None,
                description=(
                    "Telecom carrier / vendor name received from the UI "
                    "(e.g. 'vivo', 'att', 'verizon'). Used to scope fingerprint "
                    "matching and as prefix for LLM-generated rule files. "
                    "Pass 'unknown' or omit when not provided."
                ),
            ),
        ] = None,
        country: Annotated[
            _Opt[str],
            _Field(
                default=None,
                description=(
                    "Country selected by the user in the UI "
                    "(e.g. 'Brazil', 'United States'). Logged for traceability; "
                    "also used as fallback vendor hint when vendor is unknown."
                ),
            ),
        ] = None,
        max_pages: Annotated[
            _Opt[int],
            _Field(
                default=None,
                description=(
                    "Maximum number of pages to process per PDF. "
                    "Overrides the module-level MAX_PAGES constant when provided. "
                    "Pass the value supplied by the user in the UI (default 40)."
                ),
            ),
        ] = None,
    ) -> str:
        """
        Phase-1 tool: extract invoice data from one or more PDFs.

        Calls process_invoice_range() on every provided PDF (full page range),
        then stores the consolidated per-subscriber CSV into the shared session
        SQLite cache.  Returns a JSON envelope that matches what Phase 1 of
        config.yaml expects:

            {
              "success": bool,
              "extraction_complete": bool,
              "total_pdfs_processed": int,
              "total_records": int,
              "pdf_filenames": [str, ...],
              "sqlite_tables": [str, ...],
              "output_files": [str, ...],
              "errors": [str, ...],
              "processing_time_seconds": float
            }
        """
        # -1 (or any non-positive value) means "no limit — process all pages"
        effective_max_pages = (
            None if (max_pages is not None and max_pages <= 0)
            else (max_pages if max_pages is not None else MAX_PAGES)
        )

        logger.info(
            f"[TOOL] invoice_pdf_to_tables CALLED — "
            f"vendor={vendor!r}  country={country!r}  "
            f"max_pages={effective_max_pages!r}  "
            f"file_paths_count={len(file_paths) if file_paths else 0}"
        )

        # ── Resolve effective vendor ─────────────────────────────────────
        effective_vendor: _Opt[str] = None
        if vendor and vendor.lower() not in ("unknown", "none", ""):
            effective_vendor = vendor.lower()
        elif country and country.lower() not in ("unknown", "none", ""):
            # Use country as a loose vendor hint (auto-detect will still run)
            effective_vendor = None  # let fingerprint engine auto-detect
            logger.info(f"  Vendor not specified; country={country!r} — auto-detect enabled")

        # ── Collect input paths ──────────────────────────────────────────
        raw_paths: List[str] = list(file_paths) if file_paths else []

        # Normalise and deduplicate
        normalised: List[str] = []
        for p in raw_paths:
            raw = p.strip()
            lower = raw.lower()
            if lower.startswith("file://"):
                parsed = urlparse(raw)
                decoded = unquote(parsed.path or "")
                if re.match(r"^/[a-zA-Z]:/", decoded):
                    decoded = decoded[1:]
                raw = decoded.replace("/", os.sep)
            if raw and raw.lower().endswith(".pdf"):
                normalised.append(raw)

        deduped = list(dict.fromkeys(normalised))

        if not deduped:
            return json.dumps({
                "success": False,
                "extraction_complete": False,
                "error": "No PDF file paths provided. Pass file_paths=[...] with .pdf or .PDF entries.",
                "total_pdfs_processed": 0,
                "total_records": 0,
            })

        start_ts = time.time()
        successful_results: List[dict] = []
        failed_results:     List[dict] = []
        sqlite_tables:      List[str]  = []
        output_files:       List[str]  = []
        pdf_filenames:      List[str]  = []

        session_id = _get_session_id()
        # TODO: remove — debug tracing for job_id ↔ session_id identity chain
        logger.info(f"[DEBUG] job_id/session_id = {session_id!r}")
        
        # Update job status to indicate PDF processing has started
        if session_id:
            update_job_status(
                session_id,
                status="PROCESSING",
                current_phase="PHASE_1_PROCESSING",
                phase_message=f"Extracting data from {len(deduped)} PDF file(s)..."
            )
        
        for pdf_idx, pdf in enumerate(deduped, 1):
            pdf_name = os.path.basename(pdf)
            logger.info(f"  Processing PDF: {pdf_name}")

            try:
                # Open the PDF exactly once; pass the handle into
                # process_invoice_range so it doesn't re-open the file.
                with pdfplumber.open(pdf) as _pdf_obj:
                    total_pages = len(_pdf_obj.pages)
                    end_page = min(total_pages, effective_max_pages) if effective_max_pages else total_pages
                    if effective_max_pages and total_pages > effective_max_pages:
                        logger.info(
                            f"  PDF has {total_pages} pages — capping at "
                            f"max_pages={effective_max_pages} (pages 1–{end_page})"
                        )

                    per_user_results, consolidated_csv = process_invoice_range(
                        pdf_path=pdf,
                        end_page=end_page,
                        force_generate=False,
                        similarity_threshold=SIMILARITY_THRESHOLD,
                        vendor=effective_vendor,
                        pdf_obj=_pdf_obj,
                        session_id=session_id,
                    )

                # pdfplumber.open context has closed — reclaim all pdfminer
                # page/char/layout objects that accumulated during processing.
                gc.collect()
                logger.info(f"  GC sweep complete after {pdf_name}")

                ok_results = [r for r in per_user_results if r.get("success")]
                err_results = [r for r in per_user_results if not r.get("success")]

                if not ok_results and not consolidated_csv:
                    failed_results.append({
                        "pdf_filename": pdf_name,
                        "error": f"No subscriber sections extracted from {pdf_name}",
                    })
                    continue

                # ── Store consolidated CSV into SQLite ───────────────────
                if consolidated_csv and os.path.exists(consolidated_csv):
                    table_name = _gen_table_name(pdf)
                    try:
                        df = pd.read_csv(consolidated_csv)
                        if session_id:
                            _drop_table(session_id, table_name)
                            _store_df(session_id, table_name, df)
                            sqlite_tables.append(table_name)
                            logger.info(
                                f"  Stored {len(df)} subscriber row(s) into SQLite "
                                f"table '{table_name}'"
                            )
                        else:
                            logger.warning(
                                "  No active session ID — CSV written but SQLite "
                                "table NOT stored"
                            )
                        output_files.append(consolidated_csv)
                        pdf_filenames.append(pdf_name)
                        successful_results.append({
                            "pdf_filename": pdf_name,
                            "total_records": len(df),
                            "consolidated_csv": consolidated_csv,
                            "sqlite_table": table_name,
                            "subscriber_sections": len(ok_results),
                        })
                        
                        # Update progress after each PDF
                        if session_id:
                            update_job_status(
                                session_id,
                                status="PROCESSING",
                                current_phase="PHASE_1_PROCESSING",
                                phase_message=f"Processed {pdf_idx}/{len(deduped)} PDF files - extracted {len(df)} records from {pdf_name}"
                            )
                    except Exception as store_err:
                        failed_results.append({
                            "pdf_filename": pdf_name,
                            "error": f"SQLite store failed: {store_err}",
                        })
                else:
                    failed_results.append({
                        "pdf_filename": pdf_name,
                        "error": "process_invoice_range returned no output CSV",
                    })

                for er in err_results:
                    failed_results.append({
                        "pdf_filename": pdf_name,
                        "error": er.get("error", "unknown extraction error"),
                    })

            except Exception as exc:
                logger.error(f"  PDF processing failed for {pdf_name}: {exc}")
                traceback.print_exc()
                failed_results.append({
                    "pdf_filename": pdf_name,
                    "error": str(exc),
                })

        elapsed = round(time.time() - start_ts, 2)
        total_records = sum(r.get("total_records", 0) for r in successful_results)
        errors = [r.get("error") for r in failed_results if r.get("error")]

        # Update final status - mark Phase 1 as complete
        if session_id:
            if len(successful_results) > 0:
                update_job_status(
                    session_id,
                    status="PROCESSING",
                    current_phase="PHASE_1_COMPLETE",
                    phase_message=f"Phase 1 complete: extracted {total_records} records from {len(successful_results)}/{len(deduped)} PDF file(s)"
                )
            else:
                update_job_status(
                    session_id,
                    status="FAILED",
                    current_phase="PHASE_1_FAILED",
                    phase_message=f"Phase 1 failed: {len(errors)} error(s) - {'; '.join(errors[:3])}"
                )

        payload = {
            "success": len(successful_results) > 0,
            "extraction_complete": len(successful_results) > 0,
            "total_pdfs_processed": len(successful_results),
            "total_records": total_records,
            "pdf_filenames": pdf_filenames,
            "sqlite_tables": sqlite_tables,
            "output_files": output_files,
            "errors": errors,
            "processing_time_seconds": elapsed,
            "vendor_used": effective_vendor or "auto-detect",
            "country": country or "not specified",
        }

        logger.info(f"[TOOL][RESULT] {json.dumps(payload, ensure_ascii=False)}")
        return json.dumps(payload)

except ImportError:
    # agenticai SDK not available (e.g. unit tests without full install) — skip registration.
    pass