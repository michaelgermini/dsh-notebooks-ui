# Streamlit Cloud Deployment

## Structure
- `deploy_app/streamlit_app.py`: Application entrypoint
- `deploy_app/notebooks/`: Place `.ipynb` files here
- `deploy_app/requirements.txt`: App dependencies
- `deploy_app/.streamlit/config.toml`: UI preferences

## Local run
```bash
python -m pip install -r deploy_app/requirements.txt
python -m streamlit run deploy_app/streamlit_app.py
```

## Deploy to Streamlit Community Cloud
1. Create a new GitHub repository and push this `deploy_app/` folder (keep paths).
2. On Streamlit Cloud, set the app entry to `deploy_app/streamlit_app.py`.
3. Add notebooks under `deploy_app/notebooks/` (commit them or fetch at runtime).

Notes:
- The filesystem is ephemeral; generate outputs on-the-fly and serve via `st.download_button`.
- For heavy notebooks, consider disabling execution or pre-rendering HTML offline.
