from __future__ import annotations

import json
from datetime import date
import hashlib
from pathlib import Path
from typing import Any, Dict

import streamlit as st
from jinja2 import Environment, FileSystemLoader


def get_templates_directory() -> Path:
    return Path(__file__).parent / "templates"


def list_available_templates(templates_dir: Path) -> list[str]:
    return sorted([template_path.name for template_path in templates_dir.glob("*.j2")])


def get_default_context_for_template(template_name: str) -> Dict[str, Any]:
    today_string = str(date.today())

    defaults: Dict[str, Dict[str, Any]] = {
        "simple_report.html.j2": {
            "title": "Rapport de démonstration",
            "author": "Votre Nom",
            "date": today_string,
            "sections": [
                {"heading": "Introduction", "content": "Objectif du rapport et contexte."},
                {"heading": "Méthodologie", "content": "Données, outils, et procédures."},
                {"heading": "Résultats", "content": "Synthèse des résultats clés."},
                {"heading": "Conclusion", "content": "Points clés et prochaines étapes."},
            ],
        },
        "letter.md.j2": {
            "recipient_name": "Madame/Monsieur",
            "subject": "Objet de la lettre",
            "body": (
                "Je vous écris afin de vous présenter ce modèle généré via Streamlit et Jinja2.\n\n"
                "Vous pouvez adapter le contenu selon vos besoins."
            ),
            "signature": "Votre Nom",
            "date": today_string,
        },
    }

    return defaults.get(template_name, {"title": "Document", "date": today_string})


def detect_output_extension(template_name: str) -> str:
    if template_name.endswith(".html.j2"):
        return "html"
    if template_name.endswith(".md.j2"):
        return "md"
    return "txt"


def render_template_to_string(template_name: str, context: Dict[str, Any]) -> str:
    templates_dir = get_templates_directory()
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    template = env.get_template(template_name)
    return template.render(**context)


def save_output(content: str, template_name: str) -> Path:
    output_extension = detect_output_extension(template_name)
    base_name = Path(template_name).stem
    # Remove double extension patterns like .html.j2 -> .html
    base_name = base_name.replace(".html", "").replace(".md", "")

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{base_name}_output.{output_extension}"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _ui_templates_tab() -> None:
    st.title("Générateur de templates")
    st.caption("Streamlit + Jinja2")
    with st.sidebar:
        st.subheader("Export")
        st.caption("Téléchargez les rendus")
        st.markdown("- HTML: via le bouton de téléchargement après génération")
        st.markdown("- ZIP: à venir — packer plusieurs rendus")

    templates_dir = get_templates_directory()
    available_templates = list_available_templates(templates_dir)

    if not available_templates:
        st.error(
            "Aucun template trouvé. Ajoutez des fichiers .j2 dans le dossier 'templates'."
        )
        return

    selected_template = st.selectbox("Template", available_templates, index=0)

    default_context = get_default_context_for_template(selected_template)
    context_json_default = json.dumps(default_context, ensure_ascii=False, indent=2)

    st.subheader("Variables du template (JSON)")
    context_json_input = st.text_area(
        "Éditez les variables du template au format JSON",
        value=context_json_default,
        height=300,
    )

    generate_clicked = st.button("Générer le document")

    if generate_clicked:
        try:
            context = json.loads(context_json_input)
        except json.JSONDecodeError as error:
            st.error(f"JSON invalide: {error}")
            return

        try:
            rendered = render_template_to_string(selected_template, context)
        except Exception as error:  # noqa: BLE001 - surface error to UI
            st.error(f"Erreur lors du rendu du template: {error}")
            return

        output_path = save_output(rendered, selected_template)

        st.success(f"Document généré: {output_path}")

        output_extension = detect_output_extension(selected_template)
        if output_extension == "html":
            st.subheader("Aperçu HTML")
            st.components.v1.html(rendered, height=800, scrolling=True)
        elif output_extension == "md":
            st.subheader("Aperçu Markdown")
            st.markdown(rendered)
        else:
            st.subheader("Aperçu (texte)")
            st.code(rendered)

        st.download_button(
            label="Télécharger",
            data=rendered.encode("utf-8"),
            file_name=output_path.name,
            mime=(
                "text/html"
                if output_extension == "html"
                else "text/markdown" if output_extension == "md" else "text/plain"
            ),
        )


def _get_default_notebooks_directory() -> Path:
    # Prefer repo-root/notebooks if present (deployment layout),
    # otherwise fallback to repo-root/PythonDataScienceHandbook/notebooks (local sparse checkout layout).
    repo_root = Path(__file__).resolve().parents[1]
    candidate_primary = repo_root / "notebooks"
    if candidate_primary.exists():
        return candidate_primary
    return repo_root / "PythonDataScienceHandbook" / "notebooks"


def _list_notebooks(notebooks_dir: Path) -> list[Path]:
    return sorted(
        [p for p in notebooks_dir.rglob("*.ipynb") if ".ipynb_checkpoints" not in str(p)],
        key=lambda p: str(p).lower(),
    )


def _compute_notebook_cache_key(notebook_path: Path, execute: bool) -> str:
    try:
        stat_info = notebook_path.stat()
        raw_key = f"{notebook_path}:{stat_info.st_mtime_ns}:{stat_info.st_size}:{execute}"
    except FileNotFoundError:
        raw_key = f"{notebook_path}:missing:{execute}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _convert_notebook_to_html(notebook_path: Path, execute: bool) -> str:
    import nbformat  # lazy import
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import ExecutePreprocessor

    notebook_node = nbformat.read(str(notebook_path), as_version=4)

    if execute:
        ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
        ep.preprocess(notebook_node, {"metadata": {"path": str(notebook_path.parent)}})

    exporter = HTMLExporter()
    exporter.exclude_input = False
    exporter.exclude_output_prompt = True
    exporter.exclude_input_prompt = True
    body, _ = exporter.from_notebook_node(notebook_node)
    return body


@st.cache_data(show_spinner=False)
def _convert_notebook_to_html_cached(notebook_path_str: str, execute: bool, cache_key: str) -> str:
    # cache_key is used purely to invalidate the cache when file changes
    return _convert_notebook_to_html(Path(notebook_path_str), execute)


def _ui_notebooks_tab() -> None:
    st.title("Notebooks")

    default_dir = _get_default_notebooks_directory()
    notebooks_dir_str = st.text_input("Dossier notebooks", value=str(default_dir))
    notebooks_dir = Path(notebooks_dir_str)

    if not notebooks_dir.exists():
        st.error(f"Dossier introuvable: {notebooks_dir}")
        return

    notebooks = _list_notebooks(notebooks_dir)
    if not notebooks:
        st.warning("Aucun notebook .ipynb trouvé.")
        return

    selected = st.selectbox("Notebook", [str(p.relative_to(notebooks_dir)) for p in notebooks])
    selected_path = notebooks_dir / selected

    col1, col2 = st.columns([1, 1])
    with col1:
        execute_before_render = st.checkbox("Exécuter avant rendu (peut être lent)", value=False)
    with col2:
        height = st.number_input("Hauteur d'aperçu (px)", min_value=400, max_value=2000, value=900, step=50)

    if st.button("Convertir et afficher"):
        cache_key = _compute_notebook_cache_key(selected_path, execute_before_render)
        with st.spinner("Conversion en HTML en cours…"):
            try:
                html = _convert_notebook_to_html_cached(str(selected_path), execute_before_render, cache_key)
            except Exception as error:  # noqa: BLE001
                st.error(f"Erreur de conversion: {error}")
                return

        st.success("Rendu prêt")
        st.download_button(
            "Télécharger HTML",
            data=html.encode("utf-8"),
            file_name=(selected_path.stem + ".html"),
            mime="text/html",
        )
        st.components.v1.html(html, height=int(height), scrolling=True)


def main() -> None:
    st.set_page_config(page_title="Générateur de templates", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2.0rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tab_templates, tab_notebooks = st.tabs(["Templates", "Notebooks"])
    with tab_templates:
        _ui_templates_tab()
    with tab_notebooks:
        _ui_notebooks_tab()


if __name__ == "__main__":
    main()


