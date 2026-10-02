# _sp_tune.py - LIVE speaker-bubble OCR tuner.
# Passively watches the active-speaker bubble, detects WHEN the speaker
# changes, and runs several OCR configurations against each new bubble so
# the best config can be chosen from real data instead of guessed.
# READ ONLY: never presses the talk button, never speaks.
import io, json, os, re, time, collections, ctypes, hashlib
from ctypes import wintypes
import pyautogui
import pytesseract
import kaekae_bot as kb

DURATION = float(os.environ.get("TUNE_SECS", "180"))
POLL = 0.05                      # 20 Hz poll for change detection
OUT = "_sp_tune_log.jsonl"

# --- geometry: derived from the LIVE window rect on every start ---------
# The window grew 782 -> 1399 px tall, pushing the whole Talk strip down
# ~600px, so the old absolute coords now land on empty white. Anything
# cached goes stale the moment the user resizes.
_h = kb.get_camfrog_window().handle
_r = wintypes.RECT()
ctypes.windll.user32.GetWindowRect(_h, ctypes.byref(_r))
WL, WT = _r.left, _r.top

# The name sits right of the green speaker icon, which ends at x~180.
NAME_WX, NAME_WY, NAME_WW, NAME_WH = 183, 1168, 150, 30
RECT = (WL + NAME_WX, WT + NAME_WY, NAME_WW, NAME_WH)
print("window L=%d T=%d  bubble %s (window-rel %d,%d)" % (WL, WT, RECT, NAME_WX, NAME_WY))

# The name renders LIGHT BLUE on white. A "<128 dark pixel" ink test counts
# almost nothing, so the old gate called a speaking bubble EMPTY - which
# reads downstream as "room is free" and invites the bot to talk over
# whoever is actually there.
INK_TH = 200
BIN_TH = 190

def roster():
    try:
        st = json.load(io.open("bot_state.json", encoding="utf-8"))
        return [u for u in (st.get("current_room_users") or []) if u]
    except Exception:
        return []

def ink(im):
    return sum(1 for p in im.convert("L").getdata() if p < INK_TH)

def clean(s):
    return re.sub(r"[^A-Za-z0-9_$\-]", "", s or "")

# psm 7 = one line, 8 = one word, 13 = one raw line. Binarised variants are
# included because light-on-white defeats Tesseract's auto-thresholding.
CONFIGS = [
    ("p7_x4",      dict(scale=4, cfg="--psm 7",  bin=False)),
    ("p7_x4_bin",  dict(scale=4, cfg="--psm 7",  bin=True)),
    ("p8_x4_bin",  dict(scale=4, cfg="--psm 8",  bin=True)),
    ("p13_x4_bin", dict(scale=4, cfg="--psm 13", bin=True)),
    ("p6_x4_bin",  dict(scale=4, cfg="--psm 6",  bin=True)),
    ("p7_x6_bin",  dict(scale=6, cfg="--psm 7",  bin=True)),
]

def run_cfg(im, c):
    x = im.resize((im.width * c["scale"], im.height * c["scale"]))
    if c["bin"]:
        x = x.convert("L").point(lambda p: 0 if p < BIN_TH else 255, "1")
    return clean(pytesseract.image_to_string(x, config=c["cfg"]).strip())

snap = pyautogui.screenshot(region=RECT)
snap.resize((RECT[2] * 4, RECT[3] * 4)).save("_bubble.png")
d0 = ink(snap)
print("ink=%d  %s" % (d0, "(blank - nobody on mic)" if d0 < 12 else ""))
for name, c in CONFIGS:
    r = run_cfg(snap, c)
    if r:
        print("   %-12s -> %r   <-- hallucination on blank crop!" % (name, r))

R = roster()
seen_hash, last_name = None, None
log = io.open(OUT, "w", encoding="utf-8")
tally = {n: 0 for n, _ in CONFIGS}
hits = collections.Counter()
changes, t0 = 0, time.time()
print("roster: %d members - watching %ds\n" % (len(R), DURATION))

while time.time() - t0 < DURATION:
    im = pyautogui.screenshot(region=RECT)
    h = hashlib.sha1(im.tobytes()).hexdigest()
    if h == seen_hash:
        time.sleep(POLL)
        continue
    seen_hash = h
    if ink(im) < 12:
        if last_name is not None:
            print("[%6.1fs] %-22s -> <released>" % (time.time() - t0, last_name))
            last_name = None
        time.sleep(POLL)
        continue
    results = {n: run_cfg(im, c) for n, c in CONFIGS}
    names = [v for v in results.values() if v]
    best = names[0] if names else ""
    match = (best in R) if R else None
    for n, v in results.items():
        if v:
            tally[n] += 1
    hits["hit" if match else ("miss" if match is False else "noro")] += 1
    log.write(json.dumps({"t": round(time.time() - t0, 2), "from": last_name,
                          "to": best, "results": results,
                          "match": bool(match)}) + "\n")
    log.flush()
    if best != last_name:
        changes += 1
        print("[%6.1fs] %-22s -> %-22s  %s" % (
            time.time() - t0, last_name or "<none>", best or "<blank>",
            "ROSTER-OK" if match else ("not-on-roster" if R else "")))
        last_name = best or None
    time.sleep(POLL)
log.close()

print("\n=== SUMMARY (%d bubble changes) ===" % changes)
print("roster: %d hit / %d miss" % (hits["hit"], hits["miss"]))
for n, c in sorted(tally.items(), key=lambda kv: -kv[1]):
    print("   %-12s %d" % (n, c))
