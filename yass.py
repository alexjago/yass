#!/usr/bin/env python3

# Yet Another Static Site (blog generator)
# Converts markdown to html with Pandoc... 
# and generates an feed using feedgen ...
# YAML frontmatter aware too

# pip3 -r requirements.txt
# apt install pandoc | brew install pandoc

##### On with the show #####
import sys
import subprocess
from pathlib import Path
import argparse
import logging
import datetime 
import os.path

try:
    import feedgen
    import yaml
except ModuleNotFoundError:
    print("Yass: ERROR: missing dependencies. Please install them by running")
    print("    pip3 install -r path/to/yass/requirements.txt") 
    exit(1)


def make_args():
    """Process arguments for the script. 
    returns (yass args, pandoc args)"""
        
    ap = argparse.ArgumentParser(allow_abbrev=False, fromfile_prefix_chars='@',
        epilog="arguments may be stored in a config file, invoked like so: yass.py @cfg.txt    \n\
        additional arguments may be passed to pandoc like so: yass.py <yass args> -- <pandoc args>")
    
    ap.add_argument("--feed-path", default="feed.xml")
    ap.add_argument("--feed-type", default="Atom", choices=["RSS", "Atom"])
    ap.add_argument("--feed-description", "--feed-subtitle", required=True)
    ap.add_argument("--feed-link", required=True)
    ap.add_argument("--feed-title", required=True)
    ap.add_argument("--feed-logo")
    ap.add_argument("--feed-author-name", required=True)
    ap.add_argument("--feed-author-email", required=True)
    ap.add_argument("--feed-entries-count", type=int, default=-1)
    
    ap.add_argument("--regenerate", action='store_true', help="ignore all existing output")
    
    ap.add_argument("--path-root", default=".", help="directory to search and convert", type=Path)
    ap.add_argument("-c", "--css", help="URL to a CSS file to include")
    ap.add_argument("--template", type=Path, help="path to a Pandoc template file")
    ap.add_argument("-H", "--include-in-header", type=Path, help="path to an HTML fragment to include in the <head>")
    ap.add_argument("-B", "--include-before-body", type=Path, help="path to an HTML fragment of tags to include at the start of the <body>")
    ap.add_argument("-A", "--include-after-body", type=Path, help="path to an HTML fragment of tags to include at the end of the <body>")
    
    yargs, pargs = ap.parse_known_args()
    return (yargs, pargs[:1])


def make_feed(entries, yargs):
    """Take a list of (datetime, feedgen.entry)s and the program arguments 
    and create a feed file."""
    from feedgen.feed import FeedGenerator
    fg = FeedGenerator()
    
    # metadata
    fg.id(yargs.feed_link)
    fg.title(yargs.feed_title)
    fg.description(yargs.feed_description if yargs.feed_description else yargs.feed_title)
    fg.link(href=yargs.feed_link)
    
    # entries
    for ts, e in entries:
        fg.add_entry(e)
    
    # output
    if yargs.feed_type == "RSS":
        fg.rss_file(yargs.feed_path)
    elif yargs.feed_type == "Atom":
        fg.atom_file(yargs.feed_path)


def getyaml(f):
    """Get entries from the YAML header if it exists"""
    with open(f) as fp:
        s = fp.read()
        if s.startswith("---\n"):
           return yaml.safe_load(s.split("---\n")[1].split("\n...\n")[0])
        else:
            return {}

def make_entry(f, yargs, html):
    """Construct a (datetime, FeedEntry)..."""
    from feedgen.entry import FeedEntry
    
    uri = yargs.feed_link + (str(f.parent) + "/").replace("./", "") + str(f.stem) + ".html" 
    print(uri)
    
    title = str(f.stem).replace('_', ' ').title()
    updated = datetime.datetime.fromtimestamp(os.path.getmtime(f), datetime.timezone.utc)        

    # anything YAML based to get better metadata goes here too, I suppose

    y = getyaml(f)
    print(y)
    
    if "title" in y:
        title = y["title"]

    e = FeedEntry()
    e.link(href=uri)
    e.id(uri)
    e.content(html)
    e.updated(updated)
    e.title(title)
    if "date" in y:
        d = y["date"]  # anything other than the below is super messy
        e.published(datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc))
    
    if "keywords" in y:
        for k in y["keywords"]:
            e.category(category={'term': k, 'scheme': '', 'label': k})
    
    if "subtitle" in y:
        # close enough
        e.summary(y["subtitle"])
    if "abstract" in y:
        # but this is even better, if it exists
        e.summary(y["abstract"])
    
    return (updated, e)


def make_archive(entries, yargs):
    """Make an index (archive) page"""
    # title
    # subtitle/summary/abstract
    # last updated
    # keywords (under "category")
    
    docme = "---\ntitle: Archive | "+ yargs.feed_title+"\n---\n"
    
    for ue in entries[::-1]:
        e = ue[1]
        docme += "### [" + e._FeedEntry__rss_title + "](" + e._FeedEntry__rss_link + ")\n"
        if e._FeedEntry__rss_description:
            docme += e._FeedEntry__rss_description + "  \n\n"
        if e._FeedEntry__rss_pubDate:
            docme += e._FeedEntry__rss_pubDate.strftime("%Y-%m-%d")
            if e._FeedEntry__rss_lastBuildDate:
                docme +=  " (last updated " + e._FeedEntry__rss_lastBuildDate.strftime("%Y-%m-%d") + ")  \n"
        else:
            docme += e._FeedEntry__rss_lastBuildDate.strftime("%Y-%m-%d") + "\n  "
        if e._FeedEntry__rss_category:
            docme += "*" + ", ".join([x["value"] for x in e._FeedEntry__rss_category]) + "*"
        docme += "\n\n"
        
    return docme

def run():

    yargs, pargs = make_args()
    
    print(yargs)
    
    # we couldn't check for pandoc in the imports but we can now...
    try:
        subprocess.run(["pandoc", "-h"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("ERROR: could not find pandoc. Is it installed?")

    feed_entries = []
    
    basic_args = ["pandoc", "--from=markdown+yaml_metadata_block-auto_identifiers", "-t", "html5", "--ascii"]
    full_args = []
    for x in ["template", "include_in_header", "include_before_body", "include_after_body", "css"]:
        if x in vars(yargs) and vars(yargs)[x]:
            full_args.append("--" + x.replace("_", "-") + "=" + str(vars(yargs)[x]))
    if len(full_args) == 0:
        full_args.append("-s")
        
    for f in yargs.path_root.rglob("*.md"):        
        # call pandoc twice: 
        #  once for the feed content (capture), 
        #  once for the full page (write out)
        
        # pandocify invocation to crib off
        # pandoc -f markdown -t html5 --data-dir="$DATADIR" --template="$TEMPLATE" 
        #    --css="$CSSURL" --include-in-header="$HEADTAGS" 
        #    --include-before-body="$PRETAGS" --include-after-body="$POSTTAGS" 
        #    INFILE [> OUTFILE]
                
        # Pandoc #1
        rez = subprocess.run(basic_args + [str(f.expanduser().resolve())],
             stdout=subprocess.PIPE, universal_newlines=True)
             
        feed_entries.append(make_entry(f, yargs, rez.stdout))
        
        # Call Pandoc the second time...
        f_tag = str(f).replace(".md", ".html")
        if yargs.regenerate or (not os.path.exists(f_tag)) \
            or (os.path.getmtime(f) > os.path.getmtime(f_tag)):
            subprocess.run(basic_args + full_args + ["-o", str(f_tag), str(f.expanduser().resolve())])
        else:
            print("skipping", f_tag, "as it is newer")
        
                
    make_feed(sorted(feed_entries), yargs)
    arch_txt = make_archive(sorted(feed_entries), yargs)
    
    arez = subprocess.run(basic_args + full_args + 
        ["-o", str(yargs.path_root / "index.html")], 
        input=arch_txt, universal_newlines=True)
    
if __name__ == "__main__":
    run()
