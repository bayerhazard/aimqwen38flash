#!/usr/bin/env python3
"""Set engine args or top-level keys in a Strata model config.

  strata_cfgset.py <cfg.json> [--arg KEY=VALUE]... [--del-arg KEY]... [--key NAME=JSON]...
"""
import argparse, json


def kv(s):
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {s!r}")
    k, v = s.split("=", 1)
    return k, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cfg")
    ap.add_argument("--arg", type=kv, action="append", default=[])
    ap.add_argument("--del-arg", action="append", default=[])
    ap.add_argument("--key", type=kv, action="append", default=[])
    a = ap.parse_args()

    d = json.load(open(a.cfg))
    args = d["args"]
    for key, val in a.arg:
        if key in args:
            args[args.index(key) + 1] = val
        else:
            args += [key, val]
    for key in a.del_arg:
        if key in args:
            i = args.index(key)
            del args[i:i + 2]
    for name, raw in a.key:
        try:
            d[name] = json.loads(raw)
        except json.JSONDecodeError:
            d[name] = raw
    json.dump(d, open(a.cfg, "w"), indent=1)
    print("args:", " ".join(args))
    print("keys:", {k: d[k] for k in d if k in ("parallel", "aliases", "model_name", "expert_profile_save")})


if __name__ == "__main__":
    main()
