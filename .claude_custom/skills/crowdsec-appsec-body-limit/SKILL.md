---
name: crowdsec-appsec-body-limit
description: Increase (or change) the CrowdSec AppSec/WAF request body size limit for the NPMplus stack. Use when large file uploads are blocked/dropped with "request body exceeds limit N bytes" or "request body exceeded maximum allowed size" in the crowdsec logs, or when asked to raise the upload/body limit on this npmplus + crowdsec deployment.
---

# Change CrowdSec AppSec body limit (NPMplus stack)

## The key fact

The default cap is **10 MiB** (`10485760` bytes = `DefaultMaxBodySize`), enforced by the
**CrowdSec AppSec engine itself** (since v1.7.8: "WAF: enforce body size limitation"). When a
body exceeds it the request is dropped *before* the Coraza rules even run, so raising Coraza's
`SecRequestBodyLimit` does NOT fix it.

Symptom in `docker logs crowdsec`:

```
level=warning msg="request body exceeds limit 10485760 bytes, will drop request" module=acquisition.appsec
level=info    msg="WAF block: request body exceeded maximum allowed size from <ip>"
```

This cap is **not** a plain config key. `max_body_size:` / `body_size_exceeded_action:` are rejected
on both the acquisition datasource and the appsec-config struct. It is only settable via an
**`on_load` hook** using the expr helpers `SetMaxBodySize(bytes)` and
`SetBodySizeExceededAction("drop"|"partial"|"allow")`.

## Layout of this deployment

- docker-compose mounts `/opt/crowdsec/conf` → `/etc/crowdsec` (container name: `crowdsec`).
- AppSec acquisition: `/opt/crowdsec/conf/acquis.d/npmplus.yaml` (a real, editable file).
- The stock appsec-config `crowdsecurity/appsec-default` and its rules are **hub-managed symlinks**
  to `/etc/crowdsec/hub/...` — editing them gets wiped by `cscli hub upgrade`. Always use a
  **local** config file instead.

## Procedure

1. Create a local appsec-config that clones the default and adds the `on_load` hook.
   File: `/opt/crowdsec/conf/appsec-configs/appsec-custom.yaml`

   ```yaml
   name: custom/appsec-default
   default_remediation: ban
   inband_rules:
    - crowdsecurity/base-config
    - crowdsecurity/vpatch-*
    - crowdsecurity/generic-*
   outofband_rules:
    - crowdsecurity/experimental-*
    - crowdsecurity/appsec-generic-test
   # Raise the AppSec engine body cap (default 10MB / 10485760).
   # 536870912 = 512MiB. "partial" inspects up to the limit instead of dropping.
   on_load:
    - apply:
       - SetMaxBodySize(536870912)
       - SetBodySizeExceededAction("partial")
   ```

   - `SetMaxBodySize(N)` — N is **bytes**. Pick a value above the largest upload you need
     (e.g. 209715200 = 200MiB, 536870912 = 512MiB).
   - `SetBodySizeExceededAction(...)`:
     - `"drop"` (default) — block requests bigger than the limit.
     - `"partial"` — inspect up to the limit, then let the rest through (best for large uploads).
     - `"allow"` — skip body inspection entirely for oversized bodies.

2. Point the acquisition at the local config.
   In `/opt/crowdsec/conf/acquis.d/npmplus.yaml`:

   ```yaml
   appsec_config: custom/appsec-default   # was: crowdsecurity/appsec-default
   ```

3. Validate, then reload (do NOT skip validation — a bad config makes the container exit on SIGHUP):

   ```sh
   docker exec crowdsec crowdsec -t -error          # must print no fatal/error (console-enroll warning is fine)
   docker kill --signal=SIGHUP crowdsec             # reload in place
   docker logs --since 10s crowdsec | grep -iE "appsec listening|appsec-custom|level=error|fatal"
   ```

   Expect `loading .../appsec-custom.yaml` and `Appsec listening on 0.0.0.0:7422`, no errors.

4. If validation fails and the container has exited: `docker start crowdsec` after fixing the file.

## Don't forget the nginx layer

This only fixes the WAF cap. NPMplus/nginx has its own `client_max_body_size`. If uploads still
fail with a plain `413` (and no CrowdSec block appears in the logs), raise `client_max_body_size`
in the relevant NPMplus proxy host's **Advanced** config.

## To revert

Delete `appsec-configs/appsec-custom.yaml`, set `appsec_config: crowdsecurity/appsec-default`
back in `acquis.d/npmplus.yaml`, validate, and SIGHUP-reload.
