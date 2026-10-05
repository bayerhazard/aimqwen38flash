# Tuning der AIM Qwen3.8 Flash Next App (Strata)

Die Engine-Startargumente und Draft-Vokabeln liegen **nicht** im Chart, sondern in
`<appCache>/data/config/strata-iq3_xxs.json` bzw. `<appCache>/data/mtp/rt/draft_vocab.bin`.
Ein `setup`-Lauf überschreibt die Config — nach einem Reinstall die Werte unten neu anwenden
(`scripts/strata_cfgset.py`).

## Aktuelle Produktion (26.10.3): OrcaRouter Uncensored IQ3_XXS

Seit 26.10.3 läuft die **abliterierte OrcaRouter-Variante** (refusal-free Agent/Coding).
Der Chart-`MODEL_VARIANT=orca`-Pfad schreibt die getunte Config über den
`seed-strata-config`-InitContainer, sobald `packs/orca-iq3_xxs` + `models/orca-iq3_xxs`
im appCache liegen — kein `setup`-Lauf, keine Neukonfiguration. **Text-only (kein Vision).**

Seeding (einmalig pro Node, ext4/appCache):
```
# 1. Download (resumable) in <appCache>/data/models/orca-iq3_xxs/
#    orcarouter/Qwen3.8-Flash-Next-Uncensored-GGUF: IQ3_XXS-0000{1,2}-of-00002.gguf + MTP-draft.gguf
# 2. Pack im Strata-Image-Container:
STRATA_GGUF_PY=/opt/strata/third_party/llama.cpp/gguf-py .venv/bin/python tools/iq_pack.py \
  --gguf <shard1> --out /data/packs/orca-iq3_xxs --compat-bf16
# 3. MTP-Runtime /data/mtp/rt (GSQ-RCO-Draft-Head, mit dem Basismodell kompatibel — docs/ORCA.md)
```
Validiert 2026-10-05 (RTX 5090, 60-GiB-Container): space-invaders **112 t/s**, prose **107 t/s**,
Needle **25/25**, KV-Stress 32K/131K/196K **85,5/88,7/90,8 t/s**, Tool **7/7**, Agentic **30/30**.
`--kv-resident`/`parallel 2`/Conversation-Cache passen für Orca **nicht** in die 60-GiB-cgroup
(→ OOM); sie sind in der Orca-Config bewusst weggelassen.

## Validierte GSQ-RCO-Config (2026-10-04, 26.10.2 — Fallback, `MODEL_VARIANT=""`)

Ziel: stabil, `parallel 2` (ein großer + ein kleiner Kontext), minimaler Single-Stream-Impact.

Engine-Args:
```
--max-context 200000 --kv int8 --kv-resident 98304 --vision
--prefill auto:32768 --spec 4 --spec-min-p 0.70 --suffix-draft 8
--vram-reserve-mib 1024 --pool-workers 15
--conversation-cache-mib 2048 --conversation-cache-slots 2
--pcie-frac 0.20
```
Top-Level-Keys:
```json
{ "parallel": 2, "aliases": ["qwen3.8-flash-next"],
  "expert_profile_save": "/data/expert-profile-learned.bin",
  "reasoning_budget_tokens": 8192, "fit_max_tokens": true }
```
Draft-Vokabel: deutsches Subset (43 097 IDs) statt der 106 299-CJK-Datei:
```
tools/draft_vocab.py --gguf <IQ3_XXS-shard1>.gguf --base data/draft_vocab_en.bin \
  --corpus <german.txt> --coverage 0.99 --out draft_vocab_de.bin
# -> in <appCache>/data/mtp/rt/draft_vocab.bin kopieren (Backup .cjk-bak behalten)
```

Anwenden nach Reinstall (Config existiert erst nach dem ersten Setup-Lauf):
```
sudo python3 scripts/strata_cfgset.py <appCache>/data/config/strata-iq3_xxs.json \
  --arg=--prefill=auto:32768 --arg=--kv-resident=98304 --arg=--vram-reserve-mib=1024 \
  --arg=--conversation-cache-mib=2048 --arg=--conversation-cache-slots=2 \
  --key=parallel=2 --key=expert_profile_save=/data/expert-profile-learned.bin \
  --key=reasoning_budget_tokens=8192 --key=fit_max_tokens=true
# dann Pod neu: kubectl -n aimqwen38flash-shared delete pod -l io.kompose.service=vllm
```

## Warum diese Werte (gemessen)

| Parameter | Wirkung |
|---|---|
| Deutsches Draft-Vocab (43k) | de 98,9 → **117 t/s** (+18 %), Draft-Accept 47,5 → **58–62 %** |
| `--prefill auto:32768` | Prefill 2 850 → **3 100–3 160 t/s**, TTFT@196K 69 → **63 s** |
| `--kv-resident 98304` | hält langes KV im VRAM → Decode@196K **~92–110 t/s** (statt ~50 bei 32k) |
| `parallel 2` | echte Nebenläufigkeit; Single-Stream **~0 %** Impact (en 113,9/de 107,9) |

## Stabilitäts-Fallen (beide vermieden)

1. **`--vram-reserve-mib 300`** → GPU-`verify: instantiate: out of memory`. **≥1024** halten.
2. **Conversation-Parking 8192 MiB** + 2 Slots KV in gepinntem RAM → **`OOMKilled` (Host-RAM, cgroup 56 GiB)**.
   Mit `--conversation-cache-mib 2048` (die Slots sind selbst Conversation-Caches) **0 Restarts**.

## Betrieb

- **Lange Requests immer streamend** fahren. Ein nicht-streamender Request > 60 s wird am Router-Gateway mit
  502 abgeschnitten (nicht die Engine); Hermes/Wings/`benchmark.py` streamen.
- Es kann nur eine LLM-App auf der Master-GPU laufen: `aimqwen38flash` XOR `aimqwen38vllm`.
- Hilfsskripte: `scripts/strata_cfgset.py` (Config setzen), `strata-draft-probe.py` (decode + Draft-Acceptance en/de),
  `strata-concurrent-probe.py` (zwei gleichzeitige streamende Requests).

## Offen

- Container-`limitedMemory` von 56 GiB (Headroom ist unter paralleler Last knapp, ~50 GiB Ist-Verbrauch).
- Tuning als Init-/Poststart-Patch ins Chart gießen, damit ein Reinstall es ohne Handgriff bekommt.
