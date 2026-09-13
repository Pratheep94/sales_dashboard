# Business Analytics Dashboard

A single-codebase Python web app (Streamlit acts as both frontend and
backend — no separate JS needed) with multi-select business points:

1. **Monthly Sales Analysis**
2. **Monthly Product Analysis**

## Run it

```bash
pip install -r requirements.txt
```

### Set the password (required)

The app is gated behind a simple password screen. Set it via Streamlit
secrets — never hard-code it in `app.py`.

**Locally:**
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and set your own app_password
```

**On Streamlit Community Cloud:** go to your app → Settings → Secrets,
and paste:
```toml
app_password = "your-demo-password"
```

Then run:
```bash
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).
Anyone with the link will hit a password prompt before seeing any data —
share the password with your client separately from the link (e.g. a
different email/message) so the link alone isn't enough to get in.

## How to use

1. In the sidebar, tick the business point(s) you want (you can select both).
2. Upload a CSV/Excel file with columns: `Date, Product, Sales, Quantity`
   — or click **Use sample data instead** to try it with generated data.
3. View charts, tables, and summary metrics for each selected analysis.
4. Optionally **Save with joblib** to persist the computed results to disk
   (`saved_results/*.joblib`), and reload them later without recomputation.

## Where joblib is used

- `joblib.Memory` disk-caches `load_and_clean`, `monthly_sales_analysis`,
  and `monthly_product_analysis` — re-running the same data/analysis is
  instant on subsequent runs (cache lives in `cache/`).
- `joblib.dump` / `joblib.load` save and reload full analysis result
  bundles (tables + summaries) as `.joblib` files in `saved_results/`,
  so you can revisit a past run without re-uploading data.

## Extending

- Add a new business point: write an `@memory.cache`-decorated analysis
  function, add a `show_*` UI function, and add the label to
  `BUSINESS_POINTS` in `app.py`.
