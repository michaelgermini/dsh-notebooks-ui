from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


def app_root() -> Path:
    return Path(__file__).resolve().parent


def main() -> None:
    st.set_page_config(page_title="Data Science Handbook - Viewer", layout="wide")
    st.title("Python Data Science Handbook - Notebooks Viewer")

    # Prefer colocated notebooks directory for Streamlit Cloud
    notebooks_dir = app_root() / "notebooks"
    st.caption(f"Dossier notebooks: {notebooks_dir}")

    if not notebooks_dir.exists():
        st.error("Le dossier 'deploy_app/notebooks' est manquant. Ajoutez-y des .ipynb.")
        return

    notebooks = sorted(p for p in notebooks_dir.rglob("*.ipynb") if ".ipynb_checkpoints" not in str(p))
    if not notebooks:
        st.warning("Aucun notebook .ipynb trouvé.")
        return

    selected = st.selectbox("Notebook", [str(p.relative_to(notebooks_dir)) for p in notebooks])
    selected_path = notebooks_dir / selected

    execute = st.checkbox("Exécuter avant rendu", value=False)
    height = st.number_input("Hauteur (px)", min_value=400, max_value=2000, value=900, step=50)

    if st.button("Convertir et afficher"):
        with st.spinner("Conversion en HTML…"):
            html = convert_ipynb_to_html(selected_path, execute)
        st.download_button("Télécharger HTML", data=html.encode("utf-8"), file_name=selected_path.stem + ".html", mime="text/html")
        st.components.v1.html(html, height=int(height), scrolling=True)


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


if __name__ == "__main__":
    main()


