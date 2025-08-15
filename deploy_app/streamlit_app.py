from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Dict

import streamlit as st
import requests


def app_root() -> Path:
    return Path(__file__).resolve().parent


def main() -> None:
    st.set_page_config(page_title="Data Science Handbook - Viewer", layout="wide")
    st.title("Python Data Science Handbook - Notebooks Viewer")

    execute = st.checkbox("Exécuter avant rendu", value=False)
    height = st.number_input("Hauteur (px)", min_value=400, max_value=2000, value=900, step=50)

    # Unique source avec priorité GitHub, fallback local
    owner = st.text_input("Owner", value="michaelgermini")
    repo = st.text_input("Repo", value="PythonDataScienceHandbook")
    branch = st.text_input("Branche", value="master")
    directory = st.text_input("Dossier", value="notebooks")
    query = st.text_input("Filtre (contient)", value="")

    used_source = "github"
    files: List[str] = []
    with st.spinner("Chargement de la liste des notebooks…"):
        ok, files = list_ipynb_from_github(owner, repo, branch, directory)
    if (not ok) or (not files):
        # Fallback local
        used_source = "local"
        notebooks_dir = app_root() / "notebooks"
        local_files = [
            str(p.relative_to(notebooks_dir))
            for p in sorted(notebooks_dir.rglob("*.ipynb"))
            if ".ipynb_checkpoints" not in str(p)
        ] if notebooks_dir.exists() else []
        files = local_files

    if query:
        q = query.lower()
        files = [f for f in files if q in f.lower()]

    if not files:
        st.warning("Aucun notebook .ipynb trouvé.")
        return

    st.caption(f"Source utilisée: {'GitHub' if used_source=='github' else 'Local deploy_app/notebooks'}")
    selected = st.selectbox("Notebook", files)
    if st.button("Convertir et afficher"):
        if used_source == "github":
            with st.spinner("Téléchargement et conversion…"):
                ok2, html_or_msg, filename = fetch_and_convert_from_github(owner, repo, branch, selected, execute)
            if not ok2:
                st.error(html_or_msg)
                return
            html = html_or_msg
            out_name = Path(filename).stem + ".html"
        else:
            notebooks_dir = app_root() / "notebooks"
            selected_path = notebooks_dir / selected
            with st.spinner("Conversion en HTML…"):
                html = convert_ipynb_to_html(selected_path, execute)
            out_name = selected_path.stem + ".html"

        st.download_button("Télécharger HTML", data=html.encode("utf-8"), file_name=out_name, mime="text/html")
        st.components.v1.html(html, height=int(height), scrolling=True)


def convert_ipynb_to_html(nb_path: Path, execute: bool) -> str:
    import nbformat
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import ExecutePreprocessor

    node = nbformat.read(str(nb_path), as_version=4)
    if execute:
        try:
            kernel_name = (
                getattr(getattr(node, "metadata", {}), "get", lambda *_: None)("kernelspec", {}) or {}
            ).get("name") or "python3"
            ep = ExecutePreprocessor(timeout=300, kernel_name=kernel_name)
            ep.preprocess(node, {"metadata": {"path": str(nb_path.parent)}})
        except Exception:
            # Fallback: render without executing if kernel is unavailable
            pass
    exporter = HTMLExporter(template_name="classic")
    exporter.exclude_output_prompt = True
    exporter.exclude_input_prompt = True
    body, _ = exporter.from_notebook_node(node)
    return body


def list_ipynb_from_github(owner: str, repo: str, branch: str, directory: str) -> Tuple[bool, List[str]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{directory}?ref={branch}"
    resp = requests.get(url, headers=_github_headers(), timeout=20)
    if resp.status_code != 200:
        return False, f"GitHub API error {resp.status_code}: {resp.text[:200]}"
    items = resp.json()
    files = [item["path"] for item in items if item.get("type") == "file" and item.get("name", "").endswith(".ipynb")]
    # Also include subdirectories' notebooks (one level deep)
    dirs = [item["path"] for item in items if item.get("type") == "dir"]
    for d in dirs:
        sub_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{d}?ref={branch}"
        sub_resp = requests.get(sub_url, headers=_github_headers(), timeout=20)
        if sub_resp.status_code == 200:
            sub_items = sub_resp.json()
            files.extend([it["path"] for it in sub_items if it.get("type") == "file" and it.get("name", "").endswith(".ipynb")])
    files.sort(key=lambda s: s.lower())
    return True, files


def fetch_and_convert_from_github(owner: str, repo: str, branch: str, path: str, execute: bool) -> Tuple[bool, str, str]:
    import nbformat
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import ExecutePreprocessor

    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    r = requests.get(raw_url, headers=_github_headers(raw=True), timeout=30)
    if r.status_code != 200:
        return False, f"Téléchargement échoué ({r.status_code}).", path
    try:
        node = nbformat.reads(r.text, as_version=4)
        if execute:
            try:
                kernel_name = (
                    getattr(getattr(node, "metadata", {}), "get", lambda *_: None)("kernelspec", {}) or {}
                ).get("name") or "python3"
                ep = ExecutePreprocessor(timeout=300, kernel_name=kernel_name)
                ep.preprocess(node, {"metadata": {"path": "."}})
            except Exception:
                pass
        exporter = HTMLExporter(template_name="classic")
        exporter.exclude_output_prompt = True
        exporter.exclude_input_prompt = True
        body, _ = exporter.from_notebook_node(node)
        return True, body, path
    except Exception as e:  # noqa: BLE001
        return False, f"Erreur conversion: {e}", path


def _github_headers(raw: bool = False) -> Dict[str, str]:
    """Return headers for GitHub requests, using token from Streamlit secrets if available.

    Set a token in Streamlit Cloud under Secrets as:
      GITHUB_TOKEN = "ghp_xxx"  (fine-grained read-only is recommended)
    """
    headers: Dict[str, str] = {}
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN")  # type: ignore[attr-defined]
    except Exception:
        token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if not raw:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


if __name__ == "__main__":
    main()


