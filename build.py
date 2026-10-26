#!/usr/bin/env python3
"""Build the personal website and the CVs from data/*.yaml.

    python3 build.py           # website (docs/) + CV HTML + PDFs
    python3 build.py --no-pdf  # skip printing PDFs with Chrome

Outputs
    docs/index.html, docs/zh/index.html     website (publish this folder)
    docs/cv/Chao_Cheng_CV.pdf               public English CV
    docs/cv/Chao_Cheng_CV_zh.pdf            public Chinese CV
    ../cv_private/out/*.pdf                 full CVs with private fields, never published
"""
import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
BUILD = ROOT / "build"                     # intermediate CV HTML (git-ignored)
PRIVATE = ROOT.parent / "cv_private"       # outside the repo on purpose
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TODO_RE = re.compile(r"\[(?:待填|待确认)[^\]]*\]")
GROUPS = ["published", "review", "working", "book", "wip"]

LABELS = {
    "en": {
        "html_lang": "en",
        "nav_about": "About", "nav_research": "Research", "nav_books": "Books", "nav_cv": "CV",
        "nav_software": "Software", "nav_projects": "Projects", "projects": "Research Projects",
        "other_lang": "中文", "other_href": "zh/",
        "interests": "Research interests",
        "research": "Research",
        "group_published": "Publications",
        "group_review": "Papers under Review",
        "group_working": "Working Papers",
        "group_book": "Books",
        "group_wip": "Work in Progress",
        "abstract": "Abstract",
        "abstract_fallback": "Abstract",
        "with": "with",
        "and": "and",
        "authors_todo": "[待确认：署名]",
        "revision": "Revise and resubmit, *{venue}*",
        "review": "Under review, *{venue}*",
        "forthcoming": "*{venue}*, forthcoming",
        "working": "Working paper",
        "book": "Book manuscript",
        "in_chinese": " (in Chinese)",
        "cv_pdf": "CV (PDF)",
        "email": "Email",
        "updated": "Last updated",
        "expected": "Expected graduation",
    },
    "zh": {
        "html_lang": "zh-CN",
        "nav_about": "个人简介", "nav_research": "研究", "nav_books": "著作", "nav_cv": "简历",
        "nav_software": "开源软件", "nav_projects": "科研项目", "projects": "科研项目",
        "other_lang": "English", "other_href": "../",
        "interests": "研究方向",
        "research": "研究",
        "group_published": "发表论文",
        "group_review": "返修与在审论文",
        "group_working": "工作论文",
        "group_book": "著作",
        "group_wip": "在研项目",
        "abstract": "摘要",
        "abstract_fallback": "摘要（英文）",
        "with": "与",
        "and": "、",
        "authors_todo": "[待确认：署名]",
        "revision": "返修中，*{venue}*",
        "review": "在审，*{venue}*",
        "forthcoming": "*{venue}*，已录用",
        "working": "工作论文",
        "book": "书稿",
        "in_chinese": "",
        "cv_pdf": "简历（PDF）",
        "email": "邮箱",
        "updated": "最后更新",
        "expected": "预计毕业",
    },
}

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------- formatting

def fmt(text):
    """Escape, render *italic*, keep paragraph breaks, and flag TODO markers."""
    if text is None:
        return Markup("")
    s = str(escape(str(text).strip()))
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = TODO_RE.sub(lambda m: f'<span class="todo">{m.group(0)}</span>', s)
    return Markup(s)


def paras(text):
    """Split a block into <p> paragraphs (blank line or single newline in Chinese abstracts)."""
    if not text:
        return Markup("")
    chunks = [c for c in re.split(r"\n\s*\n|\n", str(text).strip()) if c.strip()]
    return Markup("".join(f"<p>{fmt(c)}</p>" for c in chunks))


def name_of(key, people, lang):
    p = people[key]
    return p[lang] if lang in p else p["en"]


def coauthor_line(pub, people, lang):
    """'with A and B' for the site; empty for solo papers."""
    L = LABELS[lang]
    others = [name_of(k, people, lang) for k in pub["authors"] if not people[k].get("self")]
    todo = "" if pub.get("authors_confirmed", True) else L["authors_todo"]
    if not others:
        return todo
    if lang == "en":
        names = others[0] if len(others) == 1 else ", ".join(others[:-1]) + " and " + others[-1]
        line = f"with {names}"
    else:
        line = f"与{'、'.join(others)}合作"
    return (line + " " + todo).strip()


def author_list(pub, people, lang):
    """Full author list for the CV, own name in bold. Uses the paper's language for Chinese papers."""
    name_lang = "zh" if (lang == "zh" and pub["lang"] == "zh") else "en"
    parts = []
    for k in pub["authors"]:
        n = str(escape(name_of(k, people, name_lang)))
        parts.append(f"<strong>{n}</strong>" if people[k].get("self") else n)
    sep = "，" if name_lang == "zh" else ", "
    s = sep.join(parts)
    if not pub.get("authors_confirmed", True):
        s += f' <span class="todo">{LABELS[lang]["authors_todo"]}</span>'
    return Markup(s)


def venue_of(pub, lang):
    v = pub["venue"]
    return v[lang] if isinstance(v, dict) else v


def status_line(pub, lang):
    L = LABELS[lang]
    if pub.get(f"status_{lang}"):
        return pub[f"status_{lang}"]
    g = pub["group"]
    if g == "review":
        return L[pub["stage"]].format(venue=venue_of(pub, lang))
    if g == "published":
        if pub["stage"] == "forthcoming":
            return L["forthcoming"].format(venue=venue_of(pub, lang))
        s = f'*{venue_of(pub, lang)}*, {pub["year"]}, {pub["volume"]}'
        if pub.get("pages"):
            s += f': {pub["pages"]}'
        return s + (L["in_chinese"] if pub["lang"] == "zh" else "")
    if g == "book":
        s = L["book"] + (L["in_chinese"] if pub["lang"] == "zh" else "")
        if pub.get("publisher"):
            s += (", " if lang == "en" else "，") + pub["publisher"]
        return s
    if g == "working":
        return L["working"] + (L["in_chinese"] if pub["lang"] == "zh" else "")
    return ""


def title_of(pub, lang):
    """Chinese page shows the original-language title; English page always shows the English title."""
    if lang == "zh" and pub.get("title_zh"):
        return pub["title_zh"]
    return pub["title_en"]


def abstract_of(pub, lang):
    """Return (text, label) for the abstract box, or (None, None)."""
    L = LABELS[lang]
    if lang == "en":
        return (pub.get("abstract_en"), L["abstract"]) if pub.get("abstract_en") else (None, None)
    if pub.get("abstract_zh"):
        return pub["abstract_zh"], L["abstract"]
    if pub.get("abstract_en"):
        return pub["abstract_en"], L["abstract_fallback"]
    return None, None


# ---------------------------------------------------------------- data

def load():
    profile = yaml.safe_load((DATA / "profile.yaml").read_text(encoding="utf-8"))
    pubs = yaml.safe_load((DATA / "publications.yaml").read_text(encoding="utf-8"))
    people = profile["people"]
    for p in pubs:
        p.setdefault("show", True)
        p.setdefault("links", {})
        assert p["group"] in GROUPS, p["id"]
        if p["group"] == "review":
            assert p.get("stage") in ("revision", "review") and p.get("venue"), p["id"]
        if p["group"] == "published":
            assert p.get("stage") in ("forthcoming", "published") and p.get("venue"), p["id"]
            if p["stage"] == "published":
                assert p.get("year") and p.get("volume"), p["id"]
        for k in p["authors"]:
            assert k in people, f"{p['id']}: unknown author key {k}"
    private = {}
    pf = PRIVATE / "private.yaml"
    if pf.exists():
        private = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
    return profile, pubs, private


def grouped(pubs, include_hidden=False):
    out = {}
    for g in GROUPS:
        items = [p for p in pubs if p["group"] == g and (p["show"] or include_hidden)]
        if items:
            out[g] = sorted(items, key=lambda p: p["order"])
    return out


# ---------------------------------------------------------------- render

def make_env(profile):
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True,
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    people = profile["people"]
    env.filters["fmt"] = fmt
    env.filters["paras"] = paras
    env.globals.update(
        coauthors=lambda p, lang: fmt(coauthor_line(p, people, lang)),
        authors=lambda p, lang: author_list(p, people, lang),
        status=lambda p, lang: fmt(status_line(p, lang)),
        title_of=title_of,
        abstract_of=abstract_of,
    )
    return env


def today_str(lang):
    d = dt.date.today()
    return f"{MONTHS_EN[d.month - 1]} {d.year}" if lang == "en" else f"{d.year} 年 {d.month} 月"


def build_site(env, profile, pubs):
    groups = grouped(pubs)
    tpl = env.get_template("site.html")
    for lang, outdir, prefix in (("en", DOCS, ""), ("zh", DOCS / "zh", "../")):
        outdir.mkdir(parents=True, exist_ok=True)
        html = tpl.render(lang=lang, L=LABELS[lang], P=profile, groups=groups,
                          prefix=prefix, updated=today_str(lang))
        (outdir / "index.html").write_text(html, encoding="utf-8")
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "assets").iterdir():
        if f.is_file() and f.name != "cv.css":
            shutil.copy2(f, DOCS / "assets" / f.name)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


def build_cvs(env, profile, pubs, private):
    """Write CV HTML files; return list of (html_path, pdf_path)."""
    BUILD.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "assets" / "cv.css", BUILD / "cv.css")
    photo = None
    if profile.get("photo"):
        src = ROOT / profile["photo"]
        if src.exists():
            shutil.copy2(src, BUILD / src.name)
            photo = src.name
    groups = grouped(pubs)
    jobs = []
    variants = [("en", False, DOCS / "cv" / "Chao_Cheng_CV.pdf"),
                ("zh", False, DOCS / "cv" / "Chao_Cheng_CV_zh.pdf"),
                ("en", True, PRIVATE / "out" / "Chao_Cheng_CV_full.pdf"),
                ("zh", True, PRIVATE / "out" / "程超_简历_应聘版.pdf")]
    for lang, full, pdf in variants:
        tpl = env.get_template(f"cv_{lang}.html")
        html = tpl.render(lang=lang, L=LABELS[lang], P=profile, groups=groups,
                          X=private if full else {}, full=full, photo=photo,
                          updated=today_str(lang), V=None)
        path = BUILD / f"cv_{lang}{'_full' if full else ''}.html"
        path.write_text(html, encoding="utf-8")
        jobs.append((path, pdf))
    # job-specific Chinese versions (summary, teaching line and section order) live in private.yaml
    for v in private.get("cv_versions", []):
        html = env.get_template("cv_zh.html").render(lang="zh", L=LABELS["zh"], P=profile, groups=groups,
                                                     X=private, full=True, photo=photo,
                                                     updated=today_str("zh"), V=v)
        path = BUILD / f"cv_zh_{v['key']}.html"
        path.write_text(html, encoding="utf-8")
        jobs.append((path, PRIVATE / "out" / v["file"]))
    return jobs


def print_pdf(html_path, pdf_path):
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           "--allow-file-access-from-files", f"--print-to-pdf={pdf_path}", html_path.as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not pdf_path.exists():
        sys.exit(f"PDF failed for {html_path.name}:\n{r.stderr}")


def report_todos(paths):
    found = {}
    for p in paths:
        text = re.sub(r"<[^>]+>", "", p.read_text(encoding="utf-8"))
        for m in TODO_RE.findall(text):
            found.setdefault(m, set()).add(p.relative_to(ROOT.parent).as_posix())
    if not found:
        print("No [待填]/[待确认] markers left.")
        return
    print(f"\n{len(found)} distinct [待填]/[待确认] markers still to resolve:")
    for m, where in sorted(found.items()):
        print(f"  {m}  ->  {', '.join(sorted(where))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pdf", action="store_true", help="skip printing PDFs")
    args = ap.parse_args()

    profile, pubs, private = load()
    env = make_env(profile)
    build_site(env, profile, pubs)
    jobs = build_cvs(env, profile, pubs, private)
    if not args.no_pdf:
        for html, pdf in jobs:
            print_pdf(html, pdf)
            print("wrote", pdf.relative_to(ROOT.parent))
    print("wrote docs/index.html, docs/zh/index.html")
    report_todos([DOCS / "index.html", DOCS / "zh" / "index.html"] + [h for h, _ in jobs])


if __name__ == "__main__":
    main()
