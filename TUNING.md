# Tuning der AIM Qwen3.8 Flash Next App (Strata)

Die Engine-Startargumente und Draft-Vokabeln liegen **nicht** im Chart, sondern in
`<appCache>/data/config/strata-iq3_xxs.json` bzw. `<appCache>/data/mtp/rt/draft_vocab.bin`.
Ein `setup`-Lauf überschreibt die Config — nach einem Reinstall die Werte unten neu anwenden
(`scripts/strata_cfgset.py`).

## Aktuelle Produktion (26.10.7): SC117 GSQ-RCO-abliterated IQ3_XXS — parallel 2 + Vision

Seit 26.10.7 läuft **SC117** (`SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF`): die
OrcaRouter-Abliteration ist in **ISTA-DASLab's GSQ-RCO-Quant** transplantiert (144
„write-to-residual-stream"-Tensoren) und behält damit die **~2-bit-Experten-Arena**.
Der Chart-`MODEL_VARIANT=sc117`-Pfad schreibt die getunte Config über den
`seed-strata-config`-InitContainer, sobald `packs/sc117-iq3_xxs`, `models/sc117-iq3_xxs`
und `mmproj-Qwen3.8-Flash-Next-BF16.gguf` im appCache liegen — kein `setup`-Lauf.

**Speicher (gemessen):** Die SC117-Arena (`gu=IQ2_XS`, `down=IQ4_NL`, Arena_total 42,91 GB)
belegt **~40 GiB** statt ~53 GiB (Orca) → **~10 GiB weniger Host-RAM** bei **200K + parallel 2
+ Vision** und gleichem/höherem Durchsatz (A/B: ~102 vs. ~85 t/s, `ram_blobs=0`, nativer
Strata-Pfad). `--kv-resident 98304`, `parallel 2`, Vision und `limitedMemory 67Gi` unverändert.
**PLE (`--ple-gguf`) = Shard 2** (nicht Shard 1 wie bei Orca).

> Historie Orca (26.10.3–26.10.6): Arena ~53 GiB anon; `--compat-bf16`-Pack nötig, weil
> Orcas IQ3_XXS Dense/Attn auf Nicht-BF16-Typen komprimiert. 26.10.7 ersetzt das durch
> SC117 (GSQ-RCO nativ, kein compat-Pack).

Seeding (einmalig pro Node, ext4/appCache):
```
# 1. Download (resumable, NICHT gated) nach <appCache>/data/models/sc117-iq3_xxs/
#    SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF: IQ3_XXS/…-0000{1,2}-of-00002.gguf
#    + mmproj-Qwen3.8-Flash-Next-BF16.gguf nach <appCache>/data/models/ (bereits vorhanden)
#    shard1 size 47342144896 sha256 03b11926…dc5 · shard2 size 28800138432 sha256 316b46f3…e113
# 2. Pack im Strata-Image-Container (OHNE --compat-bf16; GSQ-RCO ist nativ):
STRATA_GGUF_PY=/opt/strata/third_party/llama.cpp/gguf-py .venv/bin/python tools/iq_pack.py \
  --gguf <shard1> --out /data/packs/sc117-iq3_xxs
# 3. MTP-Runtime: /data/mtp/rt ist identisch mit SC117s strata/rt (dense.bin/experts.bin bytegleich)
```
Validiert 2026-10-05 (RTX 5090, 60-GiB-Container, 131K + parallel 2 + Vision):
space-invaders **112,7 t/s**, prose **106,9 t/s**, Vision liest Text korrekt,
2 gleichzeitige Requests **Overlap 23,8 s, 0 Restarts**, Needle 25/25, Tools 7/7,
Agentic 30/30. Vision-Encoder: `strata-vision` (CPU, `threads 12`, `max_tokens 300`).

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
