import io, json, os, time, collections, contextlib, sys
sys.argv = ["x"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
    import cef_probe

D = float(os.environ.get("CMP_SECS", "150"))
p = cef_probe.global_probe
p.scan_camfrog_processes()
p.attach_uia()

rows = []
t0 = time.time()
while time.time() - t0 < D:
    a = time.time()
    u = p.query_speaker_uia()
    ua = (time.time() - a) * 1000
    b = time.time()
    o = p.query_speaker_ocr()
    oa = (time.time() - b) * 1000
    if u or o:
        rows.append({"t": round(time.time() - t0, 2), "uia": u, "ocr": o,
                     "uia_ms": round(ua, 1), "ocr_ms": round(oa, 1)})
    time.sleep(0.3)

both = [r for r in rows if r["uia"] and r["ocr"]]
exact = [r for r in both if r["uia"].lower() == r["ocr"].lower()]
rep = {
    "duration_s": round(time.time() - t0, 1),
    "samples": len(rows),
    "both_read": len(both),
    "exact": len(exact),
    "agreement_pct": round(100.0 * len(exact) / len(both), 1) if both else 0.0,
    "uia_only": len([r for r in rows if r["uia"] and not r["ocr"]]),
    "ocr_only": len([r for r in rows if r["ocr"] and not r["uia"]]),
    "neither": len([r for r in rows if not r["uia"] and not r["ocr"]]),
    "uia_avg_ms": round(sum(r["uia_ms"] for r in rows) / len(rows), 1) if rows else 0,
    "ocr_avg_ms": round(sum(r["ocr_ms"] for r in rows) / len(rows), 1) if rows else 0,
}
print(json.dumps(rep, indent=2))
print()
print("--- disagreements (uia -> ocr) ---")
seen = set()
for r in rows:
    if r["uia"] and r["ocr"] and r["uia"].lower() != r["ocr"].lower():
        k = (r["uia"], r["ocr"])
        if k in seen:
            continue
        seen.add(k)
        print("  %-20s -> %-20s" % (r["uia"], r["ocr"]))
print("  (%d distinct)" % len(seen))
print()
print("--- distinct UIA speakers ---")
for k, v in collections.Counter(r["uia"] for r in rows if r["uia"]).most_common(15):
    print("  %-22s %d" % (k, v))
io.open("_sp_cmp.json", "w", encoding="utf-8").write(json.dumps(rows))
