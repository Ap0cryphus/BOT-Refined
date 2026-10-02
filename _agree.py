# _agree.py - measures OCR vs CEF agreement. Both observers are PASSIVE: nothing
# here dispatches a command, speaks, or touches the room. It only reads.
import io, json, re, sys, threading, time
import contextlib

sys.argv = ["x"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
    import cef_probe
    import ocr_capture as o
    import pyautogui

import os
DURATION = float(os.environ.get("AGREE_SECS", "180"))

def norm(s):
    """Content key: case/punctuation-insensitive, whitespace-collapsed.

    OCR never reproduces punctuation reliably, so scoring on raw text would
    measure the wrong thing. Usernames are normalised the same way but kept
    separate, because a right message from the wrong person is a real failure.
    """
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def key(user, text):
    return (norm(user), norm(text))

cef_seen, ocr_seen = {}, {}
io.open('_agree_log.txt','w',encoding='utf-8').close()

def log(m):
    io.open('_agree_log.txt','a',encoding='utf-8').write(m+chr(10))

def log(m):
    io.open('_agree_log.txt','a',encoding='utf-8').write(m+'\n')
known_users = set()
stop = threading.Event()

def cef_worker():
    probe = cef_probe.global_probe
    # scan_camfrog_processes() MUST run first: without a main_pid the attach
    # falls back to a title regex that matches both the room window and a
    # secondary CEF window, and pywinauto raises ElementAmbigousError, which
    # attach_uia() swallows into a silent False.
    probe.scan_camfrog_processes()
    if not probe.attach_uia():
        log("CEF attach FAILED - cef side will be empty")
        return
    log("CEF attached to pid %s" % getattr(probe, "main_pid", "?"))
    last = set()
    while not stop.is_set():
        try:
            for m in probe.get_chat_events(limit=200):
                if m.get("kind") != "message":
                    continue
                k = key(m.get("user"), m.get("text"))
                if k in last or not (k[0] and k[1]):
                    continue
                last.add(k)
                cef_seen[k] = {"user": m.get("user"), "text": m.get("text"),
                               "at": time.time()}
                known_users.add(m.get("user") or "")
        except Exception:
            pass
        if len(last) > 120:
            last = set(list(last)[-120:])
        time.sleep(0.35)

def _on_ocr_line(d):
    k = key(d.get("user"), d.get("text"))
    if k[0] and k[1]:
        ocr_seen[k] = {"user": d.get("user"), "text": d.get("text"),
                       "at": time.time()}
    known_users.add(d.get("user") or "")

def ocr_worker():
    reg = o.derive_feed_region()
    cap = o.ChatFeedOCR(reg, on_line=_on_ocr_line, fps=7.0, check_occlusion=True)
    t0 = time.time()
    while not stop.is_set():
        try:
            cap.sample_once()
        except Exception:
            pass
        time.sleep(cap.interval)
    stats_holder['s'] = cap.stats.snapshot()

stats_holder = {}
def run_ocr():
    stats_holder['s'] = ocr_worker()

t1 = threading.Thread(target=cef_worker, daemon=True)
t2 = threading.Thread(target=run_ocr, daemon=True)
t0 = time.time()
t1.start(); t2.start()
time.sleep(DURATION)
stop.set()
t1.join(timeout=4); t2.join(timeout=6)

cef_keys = set(cef_seen)
ocr_keys = set(ocr_seen)
both = cef_keys & ocr_keys
cef_only = cef_keys - ocr_keys
ocr_only = ocr_keys - cef_keys

def pct(a, b):
    return (100.0 * a / b) if b else 0.0

report = {
    "duration_s": round(time.time() - t0, 1),
    "cef_messages": len(cef_keys),
    "ocr_messages": len(ocr_keys),
    "matched_both": len(both),
    "cef_only_missed_by_ocr": len(cef_only),
    "ocr_only_not_in_cef": len(ocr_only),
    "agreement_pct": round(pct(len(both), len(cef_keys)), 1),
    "precision_pct": round(pct(len(both), len(ocr_keys)), 1),
    "ocr_stats": stats_holder.get("s", {}),
}
print(json.dumps(report, indent=2))

miss = [{"user": cef_seen[k]["user"], "text": cef_seen[k]["text"][:70]} for k in list(cef_only)[:25]]

# Breakdown: separate attribution failures from transcription failures.
cu={k[0] for k in cef_keys}; ou={k[0] for k in ocr_keys}
ct={k[1] for k in cef_keys}; ot={k[1] for k in ocr_keys}
u_only=sum(1 for k in cef_keys if k[0] in ou)
t_only=sum(1 for k in cef_keys if k[1] in ot)
print("\n--- BREAKDOWN (of %d CEF messages) ---" % len(cef_keys))
print("  OCR knew the USER  : %d  (%.1f%%)" % (u_only, pct(u_only,len(cef_keys))))
print("  OCR knew the TEXT  : %d  (%.1f%%)" % (t_only, pct(t_only,len(cef_keys))))
print("  OCR knew BOTH      : %d  (%.1f%%)" % (len(both), pct(len(both),len(cef_keys))))
print("  distinct users CEF=%d OCR=%d  overlap=%d" % (len(cu),len(ou),len(cu&ou)))
print("  dup OCR messages  : %d of %d" % (len(ocr_keys)-len(ot), len(ocr_keys)))

print("\n--- MISSED BY OCR (%d shown) ---" % len(miss))
for m in miss:
    print("  [%s] %s" % (m["user"][:16], m["text"]))
extra = [{"user": ocr_seen[k]["user"], "text": ocr_seen[k]["text"][:70]} for k in list(ocr_only)[:25]]
print("\n--- OCR-ONLY (%d shown) ---" % len(extra))
for m in extra:
    print("  [%s] %s" % (m["user"][:16], m["text"]))
