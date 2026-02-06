#!/usr/bin/env python3
import os, re, shlex, subprocess
from pathlib import Path
from fnmatch import fnmatch

def _split_env_list(s: str, sep=":"):
    return [x for x in (s or "").split(sep) if x]

def _split_globs(s: str):
    return [x for x in (s or "").split(":") if x]

def _is_ignored(path: str, ignore_globs):
    # normalize to forward slashes for fnmatch globs
    p = path.replace("\\", "/")
    for g in ignore_globs:
        if fnmatch(p, g):
            return True
    return False

def _ripgrep_available():
    try:
        subprocess.run(["rg", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def _keywords_from_text(text: str, max_kw=14):
    # простий extractor: слова 4..32, ASCII/latin/underscore/dash, плюс "api key" / "rate limit" і т.д.
    text = (text or "")
    base = re.findall(r"[A-Za-z0-9_:/\.\-\+]{4,32}", text)
    # dedup preserve order
    seen = set()
    kws = []
    for w in base:
        lw = w.lower()
        if lw in seen:
            continue
        seen.add(lw)
        kws.append(w)
        if len(kws) >= max_kw:
            break
    return kws

def rag_context_for_text(text: str, topk: int | None = None) -> str:
    repos = _split_env_list(os.getenv("RAG_REPOS", ""))
    if not repos:
        return ""

    topk = int(topk or os.getenv("RAG_TOPK", "6"))
    max_files = int(os.getenv("RAG_MAX_FILES", "400"))
    max_bytes = int(os.getenv("RAG_MAX_BYTES", "2000000"))
    max_snip = int(os.getenv("RAG_MAX_SNIPPET_CHARS", "1400"))

    globs = _split_globs(os.getenv("RAG_GLOBS", "README.md:docs/**:spec/**"))
    ignore = _split_globs(os.getenv("RAG_IGNORE", "**/.git/**:**/.env"))

    kws = _keywords_from_text(text)
    if not kws:
        return ""

    # Build rg query: OR of escaped keywords
    # Keep it simple: ripgrep fixed-string for each kw separately, aggregate scores.
    if not _ripgrep_available():
        return ""

    hits = []  # (score, file, line_no, line)
    file_seen = set()
    total_bytes = 0

    for repo in repos:
        repo_path = Path(repo)
        if not repo_path.exists():
            continue

        # We restrict files by glob allowlist by using rg --glob
        rg_cmd = ["rg", "-n", "--no-heading", "--hidden", "--follow"]
        for g in globs:
            rg_cmd += ["--glob", g]
        for ig in ignore:
            rg_cmd += ["--glob", f"!{ig}"]

        # Search each kw independently so we can score by occurrences
        for kw in kws:
            cmd = rg_cmd + ["-F", kw, str(repo_path)]
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            except Exception:
                continue
            if out.returncode not in (0, 1):
                continue
            for line in (out.stdout or "").splitlines():
                # format: file:line:content
                parts = line.split(":", 2)
                if len(parts) != 3:
                    continue
                f, ln, content = parts
                if _is_ignored(f, ignore):
                    continue
                key = (f, ln, content)
                # keep some duplicates (different kw) as extra score, but avoid exact dup spam
                score = 1.0
                if kw.lower() in content.lower():
                    score += 0.5
                hits.append((score, f, ln, content.strip()))

    if not hits:
        return ""

    # Aggregate per file: choose best lines; then select best files overall
    # Score file by sum of top 6 line scores
    per_file = {}
    for sc, f, ln, content in hits:
        per_file.setdefault(f, []).append((sc, int(ln), content))

    scored_files = []
    for f, arr in per_file.items():
        arr.sort(key=lambda x: (-x[0], x[1]))
        file_score = sum(x[0] for x in arr[:6])
        scored_files.append((file_score, f, arr[:10]))
    scored_files.sort(key=lambda x: -x[0])

    chunks = []
    for file_score, f, lines in scored_files[:topk]:
        if f in file_seen:
            continue
        try:
            # cap by total bytes
            st = os.stat(f)
            if total_bytes + st.st_size > max_bytes:
                continue
            total_bytes += st.st_size
        except Exception:
            pass

        file_seen.add(f)
        # Build a compact snippet
        snippet_lines = [f"- {Path(f).name} ({f})  score={file_score:.1f}"]
        for sc, ln, content in lines[:6]:
            snippet_lines.append(f"  L{ln}: {content[:240]}")
        chunk = "\n".join(snippet_lines)
        chunks.append(chunk)

        if len(chunks) >= topk:
            break
        if len(file_seen) >= max_files:
            break

    ctx = "\n\n".join(chunks).strip()
    if len(ctx) > max_snip:
        ctx = ctx[:max_snip] + "\n…(truncated)…"
    return ctx

if __name__ == "__main__":
    import sys
    q = sys.stdin.read() if not sys.argv[1:] else " ".join(sys.argv[1:])
    print(rag_context_for_text(q))
