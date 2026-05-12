from __future__ import annotations

from pathlib import Path
import subprocess

import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"
AGENTS_PATH = ROOT / "AGENTS.md"


def iteration_numbers() -> list[int]:
    numbers: set[int] = set()
    for path in ROOT.glob("RELEASE_NOTES_ITERATION_*.md"):
        try:
            numbers.add(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    for path in (ROOT / "scripts").glob("validate_iteration_*.sh"):
        try:
            numbers.add(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    return sorted(numbers)


def read_text(path: Path) -> str:
    if not path.exists():
        return f"Missing: {path}"
    return path.read_text(encoding="utf-8")


def parse_validation_summary(iteration: int) -> dict[str, str]:
    out = ARTIFACTS_DIR / f"iteration_{iteration}" / "validation_output.txt"
    summary = {
        "functionality": "n/a",
        "how": "n/a",
        "result": "unknown",
        "overall": "n/a",
    }
    if not out.exists():
        return summary
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.startswith("FUNCTIONALITY:"):
            summary["functionality"] = line.split(":", 1)[1].strip()
        elif line.startswith("HOW:"):
            summary["how"] = line.split(":", 1)[1].strip()
        elif line.startswith("RESULT:"):
            summary["result"] = line.split(":", 1)[1].strip()
        elif line.startswith("OVERALL SUMMARY:"):
            summary["overall"] = line.split(":", 1)[1].strip()
    return summary


def run_script(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 1, f"Missing script: {path}"
    proc = subprocess.run(["bash", str(path)], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def iteration_checklist(iteration: int) -> str:
    if not AGENTS_PATH.exists():
        return "Missing AGENTS.md"
    lines = AGENTS_PATH.read_text(encoding="utf-8").splitlines()
    start = f"### Iteration {iteration}"
    end = f"### Iteration {iteration + 1}"

    capture = False
    collected: list[str] = []
    for line in lines:
        if line.startswith(start):
            capture = True
        elif capture and line.startswith(end):
            break
        if capture:
            collected.append(line)

    if not collected:
        return f"No checklist section found for iteration {iteration}."
    return "\n".join(collected)


st.set_page_config(page_title="kb-ingestor human validation", layout="wide")
st.title("kb-ingestor Human Validation UI")
st.caption("Iteration-by-iteration release notes and validation artifacts")

iterations = iteration_numbers()
if not iterations:
    st.warning("No iteration artifacts found yet.")
    st.stop()

st.subheader("Validation Overview")
overview_cols = st.columns(2)
with overview_cols[0]:
    st.markdown("**Completed Iterations**")
    pass_count = 0
    for it in iterations:
        s = parse_validation_summary(it)
        status = "PASS" if s["result"] == "PASS" else "UNKNOWN"
        if status == "PASS":
            pass_count += 1
        st.write(f"Iteration {it}: {status}")
    st.write(f"Total PASS: {pass_count}/{len(iterations)}")
with overview_cols[1]:
    st.markdown("**Review Standard**")
    st.write("Each validator must show: Functionality, How, Result, and Overall Summary.")

selected = st.selectbox("Iteration", iterations, index=len(iterations) - 1)
iter_tag = f"iteration_{selected}"

release_notes = ROOT / f"RELEASE_NOTES_ITERATION_{selected}.md"
validate_script = ROOT / "scripts" / f"validate_iteration_{selected}.sh"
iter_artifacts = ARTIFACTS_DIR / iter_tag

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Selected Iteration", selected)
with col2:
    st.metric("Release Notes", "Yes" if release_notes.exists() else "No")
with col3:
    st.metric("Validation Script", "Yes" if validate_script.exists() else "No")

artifact_files = sorted(p for p in iter_artifacts.glob("**/*") if p.is_file()) if iter_artifacts.exists() else []
st.metric("Artifact Files", len(artifact_files))

st.subheader("Release Notes")
st.markdown(read_text(release_notes))

st.subheader("Iteration Checklist (AGENTS.md)")
st.code(iteration_checklist(selected), language="markdown")

st.subheader("Validation")
if st.button(f"Run validate_iteration_{selected}.sh"):
    code, output = run_script(validate_script)
    st.code(output, language="text")
    if code == 0:
        st.success("Validation script passed.")
    else:
        st.error(f"Validation script failed with exit code {code}.")

summary = parse_validation_summary(selected)
st.markdown("**Validation Summary**")
st.write(f"Functionality: {summary['functionality']}")
st.write(f"How: {summary['how']}")
st.write(f"Result: {summary['result']}")
st.write(f"Overall Summary: {summary['overall']}")
if summary["result"] == "unknown":
    st.warning("No validation summary found yet. Run the iteration validation script to generate validation_output.txt.")

st.subheader("Visible Artifacts")
if iter_artifacts.exists():
    files = artifact_files
    if files:
        for file in files:
            rel = file.relative_to(ROOT)
            with st.expander(str(rel), expanded=False):
                st.code(read_text(file), language="text")
    else:
        st.info("Artifact directory exists but no files found.")
else:
    st.info("No artifact directory for this iteration yet.")

summary_json = iter_artifacts / "run_summary_sample.json"
if summary_json.exists():
    st.subheader("Run Summary Preview")
    st.code(read_text(summary_json), language="json")

st.subheader("Run All Completed Iterations")
st.code("bash scripts/validate_all_completed_iterations.sh", language="bash")
if st.button("Run all completed validations"):
    code, output = run_script(ROOT / "scripts" / "validate_all_completed_iterations.sh")
    st.code(output, language="text")
    if code == 0:
        st.success("All completed iteration validations passed.")
    else:
        st.error(f"Validation failed with exit code {code}.")
