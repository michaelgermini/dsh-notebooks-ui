from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import streamlit as st
import requests


def app_root() -> Path:
    return Path(__file__).resolve().parent


def main() -> None:
    st.set_page_config(page_title="Data Science Handbook - Viewer", layout="wide")
    st.title("Python Data Science Handbook - Notebooks Viewer")

    source = st.radio("Source des notebooks", ["Local (deploy_app/notebooks)", "GitHub (fork)"])

    execute = st.checkbox("Exécuter avant rendu", value=False)
    height = st.number_input("Hauteur (px)", min_value=400, max_value=2000, value=900, step=50)

    if source.startswith("Local"):
        notebooks_dir = app_root() / "notebooks"
        st.caption(f"Dossier notebooks: {notebooks_dir}")
        notebooks = sorted(
            p for p in notebooks_dir.rglob("*.ipynb") if ".ipynb_checkpoints" not in str(p)
        )
        if not notebooks:
            st.warning("Aucun notebook .ipynb trouvé dans deploy_app/notebooks.")
            return
        selected = st.selectbox("Notebook", [str(p.relative_to(notebooks_dir)) for p in notebooks])
        selected_path = notebooks_dir / selected
        if st.button("Convertir et afficher"):
            with st.spinner("Conversion en HTML…"):
                html = convert_ipynb_to_html(selected_path, execute)
            st.download_button(
                "Télécharger HTML",
                data=html.encode("utf-8"),
                file_name=selected_path.stem + ".html",
                mime="text/html",
            )
            st.components.v1.html(html, height=int(height), scrolling=True)
    else:
        owner = st.text_input("Owner", value="michaelgermini")
        repo = st.text_input("Repo", value="PythonDataScienceHandbook")
        branch = st.text_input("Branche", value="master")
        directory = st.text_input("Dossier", value="notebooks")
        query = st.text_input("Filtre (contient)", value="")

        with st.spinner("Liste des notebooks depuis GitHub…"):
            ok, files = list_ipynb_from_github(owner, repo, branch, directory)
        if not ok:
            st.error(files)  # message d'erreur
            return
        if query:
            q = query.lower()
            files = [f for f in files if q in f.lower()]
        if not files:
            st.warning("Aucun notebook .ipynb trouvé (après filtre).")
            return
        selected = st.selectbox("Notebook", files)
        if st.button("Convertir et afficher"):
            with st.spinner("Téléchargement et conversion…"):
                ok2, html_or_msg, filename = fetch_and_convert_from_github(owner, repo, branch, selected, execute)
            if not ok2:
                st.error(html_or_msg)
                return
            st.download_button(
                "Télécharger HTML",
                data=html_or_msg.encode("utf-8"),
                file_name=Path(filename).stem + ".html",
                mime="text/html",
            )
            st.components.v1.html(html_or_msg, height=int(height), scrolling=True)


def convert_ipynb_to_html(nb_path: Path, execute: bool) -> str:
    import nbformat
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import ExecutePreprocessor

    node = nbformat.read(str(nb_path), as_version=4)
    if execute:
        ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
        ep.preprocess(node, {"metadata": {"path": str(nb_path.parent)}})
    exporter = HTMLExporter()
    exporter.exclude_output_prompt = True
    exporter.exclude_input_prompt = True
    body, _ = exporter.from_notebook_node(node)
    return body


def list_ipynb_from_github(owner: str, repo: str, branch: str, directory: str) -> Tuple[bool, List[str]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{directory}?ref={branch}"
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return False, f"GitHub API error {resp.status_code}: {resp.text[:200]}"
    items = resp.json()
    files = [item["path"] for item in items if item.get("type") == "file" and item.get("name", "").endswith(".ipynb")]
    # Also include subdirectories' notebooks (one level deep)
    dirs = [item["path"] for item in items if item.get("type") == "dir"]
    for d in dirs:
        sub_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{d}?ref={branch}"
        sub_resp = requests.get(sub_url, timeout=20)
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
    r = requests.get(raw_url, timeout=30)
    if r.status_code != 200:
        return False, f"Téléchargement échoué ({r.status_code}).", path
    try:
        node = nbformat.reads(r.text, as_version=4)
        if execute:
            ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
            ep.preprocess(node, {"metadata": {"path": "."}})
        exporter = HTMLExporter()
        exporter.exclude_output_prompt = True
        exporter.exclude_input_prompt = True
        body, _ = exporter.from_notebook_node(node)
        return True, body, path
    except Exception as e:  # noqa: BLE001
        return False, f"Erreur conversion: {e}", path


if __name__ == "__main__":
    main()


