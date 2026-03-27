---
name: data
description: Best practices for loading and working with data in HoloViz apps — CSV, Parquet, Arrow, Zarr, remote URLs, and streaming patterns.
metadata:
  version: "1.0.0"
  author: holoviz
  category: data-engineering
  difficulty: intermediate
---

# Data Loading Skills

Best practices for loading, profiling, and streaming data in HoloViz applications.

## Supported Formats

| Format | Library | Best For |
|--------|---------|----------|
| CSV/TSV | pandas, polars | Small-medium tabular data |
| Parquet | pandas, polars, pyarrow | Columnar analytics, large datasets |
| Arrow/Feather | pyarrow | Fast IPC, zero-copy reads |
| JSON/JSONL | pandas | API responses, log files |
| Excel | openpyxl, pandas | Business data |
| Zarr | zarr, xarray | N-dimensional arrays, chunked storage |
| NetCDF/HDF5 | xarray | Scientific/climate data |

## Loading Patterns

### Local Files

```python
import pandas as pd

# CSV
df = pd.read_csv("data.csv")

# Parquet (fast, columnar)
df = pd.read_parquet("data.parquet")

# Excel
df = pd.read_excel("data.xlsx", sheet_name="Sheet1")
```

### Remote URLs

```python
# HTTP/HTTPS
df = pd.read_csv("https://example.com/data.csv")
df = pd.read_parquet("https://example.com/data.parquet")

# S3 (requires s3fs)
df = pd.read_parquet("s3://bucket/path/data.parquet")

# GCS (requires gcsfs)
df = pd.read_parquet("gs://bucket/path/data.parquet")
```

### Zarr Arrays

```python
import xarray as xr

# Local Zarr store
ds = xr.open_zarr("data.zarr")

# Remote Zarr (S3)
ds = xr.open_zarr("s3://bucket/data.zarr")
```

## Data Profiling

When using the `load_data` MCP tool, the server returns a profile (not the data):

- Column names and dtypes
- Null counts
- Sample values (first 5 rows)
- Shape (rows x columns)
- Memory usage estimate

This keeps MCP responses small. The LLM then writes code that reads the actual data.

## Caching

```python
import panel as pn

@pn.cache(ttl=300)  # Cache for 5 minutes
def load_data(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)
```

## Streaming Data

For real-time data in Panel apps:

```python
import panel as pn
import pandas as pd
import numpy as np

pn.extension()

df = pd.DataFrame({"x": [], "y": []})
stream = hv.streams.Buffer(df, length=100)

def update():
    new = pd.DataFrame({
        "x": [pd.Timestamp.now()],
        "y": [np.random.randn()],
    })
    stream.send(new)

pn.state.add_periodic_callback(update, period=1000)
```

## Best Practices

- **Separate extraction from transformation** — keep `load_data()` functions pure
- **Cache expensive loads** with `@pn.cache` or `functools.lru_cache`
- **Use Parquet** over CSV for analytics workloads (faster, smaller, typed)
- **Use Polars** over Pandas for large in-memory datasets (faster, less memory)
- **Use DuckDB** for SQL-style analytics on DataFrames
- **Profile first** — use `load_data` tool to understand schema before plotting
- **Limit data** — sample or aggregate before visualization for large datasets
