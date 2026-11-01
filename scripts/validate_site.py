#!/usr/bin/env python3
"""Release gate for the GitHub Pages site.

Fails (exit 1) unless ALL of these hold:
  1. README.md still contains the activity-log markers, START before END.
  2. The built site has index.html and the homepage shows the README content.
  3. Every built HTML page has a doctype, a <html lang>, and a non-empty <title>.
  4. Every internal link / asset (href, src) points to a file that exists in the build.
  5. (optional) version.txt in the build matches the expected commit SHA.
"""
import argparse
import os
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote

START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"


class PageScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_doctype = False
        self.html_lang = None
        self.in_title = False
        self.title = ""
        self.links = []

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.has_doctype = True

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag == "title":
            self.in_title = True
        for attr in ("href", "src"):
            if a.get(attr) and tag in ("a", "link", "script", "img", "source", "iframe"):
                self.links.append((tag, attr, a[attr], self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def resolve(site, page_rel, url, base_path):
    p = urlparse(url)
    if p.scheme or p.netloc or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    path = unquote(p.path)
    if not path:
        return None
    if path.startswith("/"):
        if base_path and (path == base_path or path.startswith(base_path + "/")):
            path = path[len(base_path):] or "/"
        target = os.path.join(site, path.lstrip("/"))
    else:
        target = os.path.join(site, os.path.dirname(page_rel), path)
    return os.path.normpath(target)


def exists(target):
    if os.path.isdir(target):
        return os.path.isfile(os.path.join(target, "index.html"))
    return os.path.isfile(target) or os.path.isfile(target + ".html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--site", default="_site")
    ap.add_argument("--base-path", default="")
    ap.add_argument("--expect-version", default="")
    args = ap.parse_args()
    base = args.base_path.rstrip("/")
    errors = []

    try:
        readme = open(args.readme, encoding="utf-8").read()
        s, e = readme.find(START), readme.find(END)
        if s == -1 or e == -1:
            errors.append(f"{args.readme}: activity markers missing ({START} / {END})")
        elif s > e:
            errors.append(f"{args.readme}: END marker appears before START marker")
        else:
            print("[OK] README markers present")
    except FileNotFoundError:
        errors.append(f"{args.readme} not found")

    index = os.path.join(args.site, "index.html")
    if not os.path.isfile(index):
        errors.append("index.html missing from the build (is index.md there? did Jekyll run?)")
    else:
        home = open(index, encoding="utf-8", errors="replace").read()
        if "Recent activity" not in home:
            errors.append("homepage does not show the README content ('Recent activity' not found)")
        else:
            print("[OK] homepage renders the README via index.md")

    pages = links_checked = 0
    for root, _, files in os.walk(args.site):
        for name in files:
            if not name.endswith(".html"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, args.site)
            scan = PageScan()
            scan.feed(open(full, encoding="utf-8", errors="replace").read())
            pages += 1
            if not scan.has_doctype:
                errors.append(f"{rel}: missing <!doctype html>")
            if not scan.html_lang:
                errors.append(f"{rel}: <html> has no lang attribute")
            if not scan.title.strip():
                errors.append(f"{rel}: empty or missing <title>")
            for tag, attr, url, line in scan.links:
                target = resolve(args.site, rel, url, base)
                if target is None:
                    continue
                links_checked += 1
                if not exists(target):
                    errors.append(f"{rel}:{line}: broken link <{tag} {attr}=\"{url}\">")
    print(f"[OK] scanned {pages} HTML page(s), {links_checked} internal link(s)")

    if args.expect_version:
        vfile = os.path.join(args.site, "version.txt")
        got = open(vfile).read().strip() if os.path.isfile(vfile) else ""
        if got != args.expect_version:
            errors.append(f"version.txt is '{got or '<missing>'}', expected '{args.expect_version}'")
        else:
            print(f"[OK] version.txt = {got}")

    if errors:
        print(f"\n[FAIL] Release gate FAILED ({len(errors)} problem(s)):")
        for msg in errors:
            print(f"  - {msg}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error title=Release gate::{msg}")
        return 1
    print("\n[PASS] Release gate passed - safe to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())