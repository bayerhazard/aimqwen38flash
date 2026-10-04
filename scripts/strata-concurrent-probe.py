#!/usr/bin/env python3
"""Fire two concurrent requests with different prompt lengths to see how parallel slots behave.

Reports each request's actual prompt_tokens, output tokens, and duration, plus whether
both ran at the same time (wall overlap).
"""
import argparse, concurrent.futures as cf, json, os, time, urllib.request


def filler(tokens):
    block = ("The quick brown fox jumps over the lazy dog. " * 8)
    # ~4 chars/token heuristic; the server reports the real count
    return block * max(1, int(tokens * 4 / len(block)))


def call(url, key, model, prompt, max_tokens):
    body = json.dumps({"model": model, "reasoning_effort": "none", "stream": True,
                       "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.0}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            raw = r.read().decode("utf-8", "replace")
        return {"ok": True, "start": t0, "end": time.time(), "bytes": len(raw),
                "done": "[DONE]" in raw}
    except Exception as e:
        return {"ok": False, "start": t0, "end": time.time(), "err": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--api-key", default="none")
    ap.add_argument("--model", required=True)
    ap.add_argument("--a", type=int, default=150000, help="prompt-A target tokens")
    ap.add_argument("--b", type=int, default=25000, help="prompt-B target tokens")
    ap.add_argument("--max-tokens", type=int, default=64)
    a = ap.parse_args()

    pa = f"[A {os.urandom(4).hex()}]\n" + filler(a.a) + "\nSummarize in one short sentence."
    pb = f"[B {os.urandom(4).hex()}]\n" + filler(a.b) + "\nSummarize in one short sentence."
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(call, a.url, a.api_key, a.model, pa, a.max_tokens)
        fb = ex.submit(call, a.url, a.api_key, a.model, pb, a.max_tokens)
        ra, rb = fa.result(), fb.result()
    overlap = min(ra["end"], rb["end"]) - max(ra["start"], rb["start"])
    print(f"A ({a.a} target): {ra}")
    print(f"B ({a.b} target): {rb}")
    print(f"wall={time.time()-t0:.1f}s overlap={overlap:.1f}s  (overlap>0 => ran together)")


if __name__ == "__main__":
    main()
