from typing import List


def generate_table_of_contents(sections: List[str]) -> str:
    """Generates a Markdown Table of Contents from a list of section names."""
    lines = ["## Tabla de Contenidos\n"]
    for s in sections:
        anchor = s.lower().replace(" ", "-").replace("/", "").replace(".", "")
        lines.append(f"- [{s}](#{anchor})")
    return "\n".join(lines)
