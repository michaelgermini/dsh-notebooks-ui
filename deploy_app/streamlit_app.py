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
    apply_css = st.checkbox("Appliquer style personnalisé", value=True)
    default_css = (
        """
        :root { color-scheme: light dark; }
        html { scroll-behavior: smooth; }
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Arial, sans-serif; max-width: 980px; margin: 2rem auto; padding: 0 1.2rem; line-height: 1.65; }
        h1, h2, h3, h4 { line-height: 1.25; }
        img, svg, canvas, video { max-width: 100%; height: auto; }
        table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        th, td { border-bottom: 1px solid #ddd; padding: 0.5rem; text-align: left; }
        pre, code, kbd { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
        pre { background: rgba(0,0,0,0.06); padding: 0.75rem; border-radius: 8px; overflow: auto; }
        .code-cell pre { background: #111; color: #eee; }
        blockquote { border-left: 4px solid #999; margin: 1rem 0; padding: 0.25rem 0.75rem; color: #666; }
        hr { border: none; border-top: 1px solid #ccc; margin: 2rem 0; }
        .md-cell pre { background: transparent; }
        """
    )
    css_text = st.text_area("CSS", value=default_css, height=180) if apply_css else ""

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
            html = inject_custom_css(html_or_msg, css_text) if apply_css else html_or_msg
            out_name = Path(filename).stem + ".html"
        else:
            notebooks_dir = app_root() / "notebooks"
            selected_path = notebooks_dir / selected
            with st.spinner("Conversion en HTML…"):
                base_html = convert_ipynb_to_html(selected_path, execute)
                html = inject_custom_css(base_html, css_text) if apply_css else base_html
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
    return _export_notebook_html(node)


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
        body = _export_notebook_html(node)
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


def _export_notebook_html(node) -> str:
    """Export notebook node to HTML with robust fallbacks.

    Tries nbconvert templates in order, then falls back to a minimal renderer.
    """
    # Try 'classic'
    try:
        exp = HTMLExporter(template_name="classic")
        exp.exclude_output_prompt = True
        exp.exclude_input_prompt = True
        body, _ = exp.from_notebook_node(node)
        return body
    except Exception:
        pass

    # Try 'basic'
    try:
        exp = HTMLExporter(template_name="basic")
        exp.exclude_output_prompt = True
        exp.exclude_input_prompt = True
        body, _ = exp.from_notebook_node(node)
        return body
    except Exception:
        pass

    # Minimal fallback
    try:
        cells_html = []
        for cell in node.get("cells", []):
            ctype = cell.get("cell_type")
            src = "".join(cell.get("source", []))
            if ctype == "markdown":
                cells_html.append(f"<div class=\"md-cell\"><pre>{_html_escape(src)}</pre></div>")
            elif ctype == "code":
                cells_html.append(f"<div class=\"code-cell\"><pre><code>{_html_escape(src)}</code></pre></div>")
            else:
                cells_html.append(f"<div class=\"raw-cell\"><pre>{_html_escape(src)}</pre></div>")
        return (
            "<!doctype html><meta charset='utf-8'><style>body{font-family:system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.6}.code-cell pre{background:#111;color:#eee;padding:0.75rem;border-radius:6px;overflow:auto}</style>"
            + "".join(cells_html)
        )
    except Exception:
        return "<p>Impossible de convertir le notebook en HTML.</p>"


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def inject_custom_css(html: str, css: str) -> str:
    """Insert a <style> tag with provided CSS into HTML string.

    If a <head> tag exists, inject inside it; otherwise prepend the style.
    """
    if not css.strip():
        return html
    style_tag = f"<style>\n{css}\n</style>"
    lower = html.lower()
    head_idx = lower.find("<head>")
    if head_idx != -1:
        insert_at = head_idx + len("<head>")
        return html[:insert_at] + style_tag + html[insert_at:]
    # If there is a <html> but no head, create one after <html>
    html_idx = lower.find("<html")
    if html_idx != -1:
        # Find end of <html ...>
        end_tag = lower.find(">", html_idx)
        if end_tag != -1:
            insert_at = end_tag + 1
            return html[:insert_at] + "<head>" + style_tag + "</head>" + html[insert_at:]
    # Fallback: prepend
    return style_tag + html


if __name__ == "__main__":
    main()


