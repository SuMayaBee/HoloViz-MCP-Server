"""Data source resolution and chart recommendation helpers.

Handles Kaggle downloads, HuggingFace downloads, and auto chart suggestions.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_kaggle_source(source: str) -> str | dict:
    """Download a Kaggle dataset/competition and return the local file path.

    Returns a file path string on success, or an error dict if credentials are
    missing or the download fails.
    """
    import re
    import tempfile

    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")

    if not username or not key:
        return {
            "error": (
                "Kaggle API credentials not provided. "
                "Add KAGGLE_USERNAME and KAGGLE_KEY to the env section of your MCP config:\n"
                '  "env": { "KAGGLE_USERNAME": "your_username", "KAGGLE_KEY": "your_api_key" }\n'
                "Get your API key at https://www.kaggle.com → Account → Settings → Create New Token."
            ),
            "source": source,
        }

    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key

    try:
        import kaggle  # noqa: PLC0415
    except ImportError:
        return {
            "error": 'kaggle package is not installed. Reinstall with the \'kaggle\' extra: uvx --from "hvmcp[kaggle]" hvmcp mcp',
            "source": source,
        }

    download_dir = tempfile.mkdtemp(prefix="holoviz_kaggle_")

    dataset_match = re.search(r"kaggle\.com/datasets/([^/?#]+/[^/?#]+)", source)
    competition_match = re.search(r"kaggle\.com/competitions/([^/?#]+)", source)

    try:
        if dataset_match:
            slug = dataset_match.group(1)
            kaggle.api.authenticate()
            kaggle.api.dataset_download_files(slug, path=download_dir, unzip=True)
        elif competition_match:
            slug = competition_match.group(1)
            kaggle.api.authenticate()
            kaggle.api.competition_download_files(slug, path=download_dir)
        else:
            return {"error": f"Could not parse Kaggle URL: {source}", "source": source}
    except Exception as e:
        return {"error": f"Kaggle download failed: {e}", "source": source}

    for ext in ("*.csv", "*.parquet", "*.tsv", "*.json"):
        matches = list(Path(download_dir).rglob(ext))
        if matches:
            return str(matches[0])

    return {"error": "No CSV/Parquet/TSV/JSON file found in the downloaded Kaggle dataset.", "source": source}


def resolve_huggingface_source(source: str) -> str | dict:
    """Download a HuggingFace dataset and return the local file path.

    Returns a file path string on success, or an error dict on failure.
    HF_TOKEN env var is optional — only needed for private datasets.
    """
    import re
    import tempfile

    match = re.search(r"huggingface\.co/datasets/([^/?#]+/[^/?#]+)", source)
    if not match:
        return {"error": f"Could not parse HuggingFace dataset URL: {source}", "source": source}

    repo_id = match.group(1)
    token = os.environ.get("HF_TOKEN")

    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
        from huggingface_hub import list_repo_files  # noqa: PLC0415
    except ImportError:
        return {
            "error": 'huggingface_hub package is not installed. Reinstall with the \'huggingface\' extra: uvx --from "hvmcp[huggingface]" hvmcp mcp',
            "source": source,
        }

    try:
        download_dir = tempfile.mkdtemp(prefix="holoviz_hf_")
        all_files = list(list_repo_files(repo_id, repo_type="dataset", token=token))
        target = next(
            (f for f in all_files if f.endswith(".parquet")),
            next((f for f in all_files if f.endswith(".csv")), None),
        )
        if not target:
            return {"error": f"No Parquet or CSV file found in HuggingFace dataset '{repo_id}'.", "source": source}

        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=target,
            repo_type="dataset",
            token=token,
            local_dir=download_dir,
        )
        return local_path

    except Exception as e:
        return {"error": f"HuggingFace download failed: {e}", "source": source}


def recommend_charts(profile: dict) -> list[dict]:
    """Analyse a dataset profile and return up to 3 chart recommendations with ready-to-run code."""
    source = profile["source"]
    rows = profile["shape"]["rows"]
    columns = profile["columns"]

    numeric_cols = [c["name"] for c in columns if c["dtype"] in ("int64", "float64", "int32", "float32")]
    categorical_cols = [c["name"] for c in columns if c["dtype"] in ("object", "category", "bool") and c["unique"] < 50]
    datetime_cols = [
        c["name"]
        for c in columns
        if "datetime" in c["dtype"] or any(k in c["name"].lower() for k in ("date", "time", "year", "month"))
    ]

    large = rows > 100_000
    datashade_arg = ", datashade=True" if large else ""

    src_lower = source.lower()
    if src_lower.endswith(".parquet"):
        reader = f'pd.read_parquet("{source}")'
    elif src_lower.endswith(".tsv"):
        reader = f'pd.read_csv("{source}", sep="\\t")'
    else:
        reader = f'pd.read_csv("{source}")'

    recs: list[dict] = []

    if datetime_cols and numeric_cols:
        t, v = datetime_cols[0], numeric_cols[0]
        recs.append({
            "type": "line",
            "title": f"{v} over time",
            "reason": f"Datetime column '{t}' + numeric column '{v}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f'df = {reader}\ndf["{t}"] = pd.to_datetime(df["{t}"])\n'
                f'df.hvplot.line(x="{t}", y="{v}"{datashade_arg}, title="{v} over time")'
            ),
        })

    if len(numeric_cols) >= 2:
        x, y = numeric_cols[0], numeric_cols[1]
        color_arg = f', by="{categorical_cols[0]}"' if categorical_cols else ""
        recs.append({
            "type": "scatter",
            "title": f"{x} vs {y}",
            "reason": f"Two numeric columns '{x}' and '{y}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.hvplot.scatter(x="{x}", y="{y}"{color_arg}{datashade_arg}, title="{x} vs {y}")'
            ),
        })

    if categorical_cols and numeric_cols:
        cat, val = categorical_cols[0], numeric_cols[0]
        recs.append({
            "type": "bar",
            "title": f"{val} by {cat}",
            "reason": f"Categorical column '{cat}' + numeric column '{val}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.groupby("{cat}")["{val}"].mean().hvplot.bar(title="{val} by {cat}", rot=45)'
            ),
        })

    if len(recs) < 3 and numeric_cols:
        val = numeric_cols[0]
        recs.append({
            "type": "histogram",
            "title": f"Distribution of {val}",
            "reason": f"Numeric column '{val}' available for distribution analysis",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.hvplot.hist("{val}", bins=30, title="Distribution of {val}")'
            ),
        })

    return recs[:3]
