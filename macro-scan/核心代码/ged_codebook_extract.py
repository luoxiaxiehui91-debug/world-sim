import sys
sys.path.insert(0, r"C:/Users/luoxi/.workbuddy/binaries/python/envs/gedpdflib")
from pypdf import PdfReader

PATH = r"S:/20260729/ged261.pdf"
r = PdfReader(PATH)
print("PAGES:", len(r.pages))
full = []
for i, p in enumerate(r.pages):
    try:
        t = p.extract_text() or ""
    except Exception as e:
        t = ""
    full.append(t)
alltext = "\n".join(full)
print("TOTAL CHARS:", len(alltext))

terms = ["type of violence", "state-based", "non-state", "one-sided", "where_prec",
         "date_prec", "best", "high", "low", "deaths", "PRIO-GRID", "geom_wkt",
         "priogrid", "number of sources", "event_clarity", "conflict_dset"]
for term in terms:
    idx = alltext.lower().find(term.lower())
    if idx >= 0:
        seg = alltext[max(0,idx-200):idx+400]
        print("\n========== TERM:", term, "==========")
        print(seg)
    else:
        print("\n[not found]:", term)
