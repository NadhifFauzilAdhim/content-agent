# 08 · API reference

Base path: `/api/v1`. Authentication: httpOnly cookie `factory_session` (set by `/auth/login`) or
`Authorization: Bearer <jwt>` for machine clients. Errors use one envelope:

```json
{ "error": { "code": "forbidden", "message": "Requires the admin role (you are editor)", "details": null } }
```

Interactive docs: `/docs` (disabled in production). RBAC is noted per endpoint.

## Health & config

| method | path | role | notes |
|---|---|---|---|
| GET | `/healthz` | public | liveness |
| GET | `/readyz` | public | DB reachability + ffmpeg presence |
| GET | `/auth/config` | public | which integrations are configured (no secrets) |
| GET | `/system/status` | member | services, providers, scheduler |
| GET | `/system/integrations` | member | OAuth/storage/vault/ffmpeg flags |

## Auth

| method | path | role | notes |
|---|---|---|---|
| POST | `/auth/login` | public | rate-limited; sets session cookie |
| POST | `/auth/logout` | member | clears cookie, audits |
| GET | `/auth/session` | member | user + workspace + role |
| POST | `/auth/password` | member | change own password |

## Channels

| method | path | role | notes |
|---|---|---|---|
| GET/POST | `/channels` | member / editor | list / create (creates settings + schedule) |
| GET/PATCH/DELETE | `/channels/{id}` | member / editor / admin | soft delete (archive) |
| PUT | `/channels/{id}/characters` | editor | replace the cast |
| GET/POST | `/channels/{id}/schedules` | member / editor | schedule CRUD |
| PATCH/DELETE | `/schedules/{id}` | editor | update / delete |
| POST | `/channels/{id}/youtube/connect` | editor | returns Google consent URL |
| POST | `/channels/{id}/youtube/disconnect` | admin | revoke stored tokens |
| GET | `/youtube/status` | member | OAuth config + connections |
| GET | `/youtube/callback` | public | Google redirect target (state-checked) |

## Content

| method | path | role | notes |
|---|---|---|---|
| GET | `/content?channel_id&status&q&limit` | member | project list |
| GET | `/content/{id}` | member | script, scenes, assets, renders, QC, workflow |
| PATCH | `/content/{id}` | editor | title + SEO metadata |
| POST | `/content/{id}/regenerate` | editor | script/storyboard regeneration (new run) |
| POST | `/content/{id}/scenes/{index}/regenerate?target=image\|audio` | editor | per-scene repair |
| DELETE | `/content/{id}` | editor | archive |
| GET | `/content/{id}/download` | member | MP4 (local storage backend) |
| GET | `/files/{key}` | member | assets/images/audio with traversal protection |

## Workflows

| method | path | role | notes |
|---|---|---|---|
| GET | `/workflows?status&channel_id&limit` | member | monitor list |
| POST | `/workflows?channel_id&force_approval` | editor | start production (returns 201 immediately) |
| GET | `/workflows/{id}` | member | detail + tasks + logs |
| POST | `/workflows/{id}/retry` | editor | failed/pending runs, bounded by `max_retries` |
| POST | `/workflows/{id}/cancel` | editor | terminal |

## Agents

| method | path | role | notes |
|---|---|---|---|
| GET | `/agents` | member | registry with 30-day performance |
| GET | `/agents/{key}` | member | one agent |
| PUT | `/agents/{key}/config` | admin | provider, model, temperature, prompt, enabled |
| GET | `/agents/{key}/runs` | member | recent task rows |

## Providers

| method | path | role | notes |
|---|---|---|---|
| GET/POST | `/providers` | member / admin | list / add (key encrypted, never returned) |
| GET | `/providers/{id}` | member | one provider (metadata only) |
| PATCH | `/providers/{id}` | admin | update (enable/disable, models, base URL, defaults) |
| DELETE | `/providers/{id}` | admin | **permanently delete**: clears agent bindings, shreds credentials, keeps usage history |
| POST | `/providers/{id}/test` | editor | live connection test → health + checks |
| GET | `/providers/{id}/models` | editor | models from the endpoint (`?refresh=true&persist=true` saves them) |
| POST | `/providers/discover-models` | editor | list models for an unsaved endpoint `{slug, base_url, api_key}` |
| GET | `/providers/adapters` | member | supported adapters per kind |
| GET | `/providers/voices/{id}` | member | TTS voice catalogue (legacy shape) |
| GET | `/providers/encryption` | member | `{ready, problem, algorithm}` for the vault |
| GET | `/providers/{kind}/{slug}/credentials` | admin | credential metadata (fingerprint, version, status) |
| POST | `/providers/{kind}/{slug}/credentials` | admin | merge a new key + TTS defaults (empty values ignored) |
| PUT | `/providers/{kind}/{slug}/credentials` | admin | rotate (key required) |
| DELETE | `/providers/{kind}/{slug}/credentials` | admin | shred the key, keep history |
| GET | `/providers/youtube/google/client` | editor | Google OAuth client state (masked id, source, redirect URI) |
| PUT | `/providers/youtube/google/client` | admin | store the Google client id + secret (encrypted; blank secret keeps the stored one) |
| DELETE | `/providers/youtube/google/client` | admin | remove the dashboard client (environment values, if any, take over) |

## Text to speech

| method | path | role | notes |
|---|---|---|---|
| GET | `/tts/providers` | member | configured TTS providers, key state, defaults |
| GET | `/tts/providers/{slug}` | member | provider + models, params, output formats |
| GET | `/tts/models` | member | models per provider (`?provider=`) |
| GET | `/tts/voices` | member | voices per provider (`?provider=&language=&query=`) |
| GET | `/tts/voices/{provider}/{voice}/preview` | member | proxied voice sample (key never exposed) |
| POST | `/tts/generate` | editor | `{text, provider?, model?, voice_id?, language?, output_format?, voice_settings?}` |
| POST | `/tts/generate-dialogue` | editor | multi-speaker lines (provider must support dialogue) |
| POST | `/tts/compare` | editor | one text, two configurations, side-by-side metrics |
| GET | `/tts/generations` | member | history (`provider, status, trigger, limit, offset`) |
| GET | `/tts/generations/{id}` | member | one generation incl. chunk manifest |
| GET | `/tts/usage` | member | totals, by provider / model / day (`?days=`) |
| GET | `/tts/estimate` | member | cost estimate for a character count |
| GET | `/tts/settings` · PUT | member / admin | workspace default + fallback |
| GET | `/tts/channels/{id}` · PUT | member / admin | channel voice override |
| GET | `/tts/debug/resolved` | member | effective configuration with the level that supplied each value |
| POST | `/tts/test` | editor | short synthesis used by the connection test |

Rate limits: 30 generations/min and 10 comparisons/min per user.

## Video engine (Remotion)

| method | path | role | notes |
|---|---|---|---|
| GET | `/video/engine` | member | Node/Remotion status, templates, transitions |
| GET | `/video/templates` | member | template ids, palettes, aspect ratios |
| POST | `/video/projects/{project_id}/renders` | editor | queue a render → `202` `{kind: full\|scene\|preview}` |
| GET | `/video/projects/{project_id}/renders` | member | render history for a project |
| GET | `/video/renders/{job_id}` | member | job detail (status, progress, output URL) |
| GET | `/video/renders/{job_id}/status` | member | poll: stage, progress, ETA |
| POST | `/video/renders/{job_id}/cancel` | editor | stop via Remotion's cancel signal |
| POST | `/video/renders/{job_id}/retry` | editor | re-queue a failed/cancelled render |
| GET | `/video/renders/{job_id}/spec` | member | exact storyboard props fed to Remotion |
| GET | `/video/renders/{job_id}/validation` | member | ffprobe checks (dimensions, fps, audio, A/V sync) |
| GET | `/video/summary` | member | engine status + job counts by status |

See [10 - Video engine](10-video-engine.md) for the composition model and pipeline.

## Approvals, costs, analytics, workspace

| method | path | role | notes |
|---|---|---|---|
| GET | `/approvals?status` | member | default pending |
| POST | `/approvals/{id}/decision` | editor | `{decision: approve\|reject, note}` — approval triggers publish |
| POST | `/approvals/{id}/expire` | admin | manual expiry |
| GET | `/costs` | member | ledgers, daily series, budgets |
| GET | `/costs/ledger` | member | raw usage rows |
| PUT | `/costs/budget` | admin | monthly + per-video ceiling |
| GET | `/analytics?days` | member | snapshots, trend, videos |
| POST | `/analytics/sync` | editor | collect from YouTube Analytics |
| GET | `/overview` | member | dashboard projection (all values from rows) |
| GET | `/workspace`, `/workspace/members` | member | workspace + team |
| POST/DELETE | `/workspace/members` | admin | invite / remove |
| GET | `/workspace/audit` | admin | audit trail |
| GET/POST/DELETE | `/workspace/api-keys` | admin | machine keys (shown once) |
