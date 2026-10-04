#!/usr/bin/env python3
"""Focused Strata-app probe: decode t/s + MTP draft acceptance, German and English.

Unlike benchmark.py (which drops the draft fields), this reads the engine's
`timings` block (draft_n / draft_n_accepted) so a draft-vocabulary change is
measurable. Uses a unique cache nonce per request.
"""
import argparse, json, os, statistics, time, urllib.request

TASKS = {
    "en": "Write a detailed technical paragraph of about 200 words describing how a "
          "transformer's attention mechanism works, and why caching the key/value "
          "tensors speeds up long-context inference.",
    "de": "Schreibe einen ausfuehrlichen technischen Absatz von etwa 200 Woertern darueber, "
          "wie der Hermes-Agent Werkzeuge auswaehlt, Fehler erkennt und mehrstufige "
          "Aufgaben plant; erklaere auch, warum ein grosser Kontext dabei hilft.",
}


def call(url, key, model, prompt, max_tokens, effort):
    body = json.dumps({
        "model": model, "reasoning_effort": effort,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def run(url, key, model, lang, runs, max_tokens, effort):
    dec, acc = [], []
    for i in range(runs):
        p = f"[probe {lang} {os.urandom(6).hex()} {i}]\n\n" + TASKS[lang]
        d = call(url, key, model, p, max_tokens, effort)
        t = d.get("timings", {})
        n, ms = t.get("predicted_n", 0), t.get("predicted_ms", 1)
        if n and ms:
            dec.append(n / (ms / 1000))
        dn, da = t.get("draft_n", 0), t.get("draft_n_accepted", 0)
        if dn:
            acc.append(da / dn)
    dm = round(statistics.median(dec), 1) if dec else 0
    am = round(100 * statistics.median(acc), 1) if acc else 0
    print(f"  {lang}: decode {dm} t/s (n={len(dec)}) | draft-accept {am}%")
    return dm, am


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--api-key", default="none")
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--effort", default="none")
    ap.add_argument("--langs", nargs="+", default=["en", "de"])
    a = ap.parse_args()
    print(f"probe url={a.url} model={a.model} runs={a.runs}")
    for lang in a.langs:
        run(a.url, a.api_key, a.model, lang, a.runs, a.max_tokens, a.effort)


if __name__ == "__main__":
    main()
