"""Template-based code generation for Streamlit Databricks Apps."""

from __future__ import annotations

from pathlib import Path

from composer.models.blueprint import AppBlueprint


def generate_streamlit_app(blueprint: AppBlueprint, output_root: str) -> dict:
    app_dir = Path(output_root) / f"generated_{blueprint.blueprint_id[:8]}"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_py = app_dir / "app.py"
    app_yaml = app_dir / "app.yaml"
    readme = app_dir / "README.md"

    app_py.write_text(
        "import streamlit as st\n"
        f"st.title('Generated App {blueprint.blueprint_id[:8]}')\n"
        f"st.write('Pages: {', '.join(blueprint.pages)}')\n",
        encoding="utf-8",
    )
    app_yaml.write_text("name: generated-app\ncommand: streamlit run app.py\n", encoding="utf-8")
    readme.write_text("# Generated Databricks App\n", encoding="utf-8")

    return {
        "output_path": str(app_dir),
        "files_generated": [str(app_py), str(app_yaml), str(readme)],
    }
