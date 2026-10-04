{{- /* aimqwen38flash.supports: expand the market's short capability groups
       (`thinking,tools,vision`) into llm-init's supports_* keys. `vision`
       false drops the capability where the engine would refuse images. */ -}}
{{- define "aimqwen38flash.supports" -}}
{{- $keys := list -}}
{{- range splitList "," .supports -}}
{{- $s := trim . -}}
{{- if eq $s "thinking" -}}
{{- $keys = concat $keys (list "supports_reasoning" "supports_reasoning_effort") -}}
{{- else if eq $s "tools" -}}
{{- $keys = concat $keys (list "supports_function_calling" "supports_parallel_function_calling" "supports_tool_choice") -}}
{{- else if eq $s "vision" -}}
{{- if $.vision -}}{{- $keys = append $keys "supports_vision" -}}{{- end -}}
{{- else if not (or (eq $s "none") (eq $s "")) -}}
{{- fail (printf "MODEL_SUPPORTS: %q is not one of thinking, tools, vision, none" $s) -}}
{{- end -}}
{{- end -}}
{{- join "," $keys -}}
{{- end -}}
