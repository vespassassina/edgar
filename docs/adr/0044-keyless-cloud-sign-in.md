# ADR-0044 — Sign in to Azure, Google Cloud and AWS through the cloud's own CLI

**Status:** Accepted · 2026-09-14 · Adds PRV-20 (Core); amends CFG-6

## Context

The maintainer asked for OAuth sign-in to the models on Azure, AWS and Google
Cloud, not only keys, because Azure is phasing keys out.

Checked on 2026-09-14:

- **Azure OpenAI** accepts a Microsoft Entra ID token as
  `Authorization: Bearer`, with the scope `https://cognitiveservices.azure.com/.default`
  and the role "Cognitive Services OpenAI User". An organisation can switch keys
  off with Azure Policy ("disable local auth"), and Microsoft's own samples now
  start keyless
  ([Microsoft Learn: keyless connections](https://learn.microsoft.com/en-us/azure/developer/ai/keyless-connections)).
- **Google Vertex AI** serves Gemini and partner models on an OpenAI-compatible
  endpoint,
  `https://LOCATION-aiplatform.googleapis.com/v1beta1/projects/PROJECT/locations/LOCATION/endpoints/openapi`,
  and takes an OAuth access token as bearer, for example from
  `gcloud auth print-access-token`. It has no API keys for this endpoint
  ([Vertex AI: OpenAI compatibility](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/call-vertex-using-openai-library)).
- **Amazon Bedrock** serves models on an OpenAI-compatible endpoint,
  `https://bedrock-runtime.REGION.amazonaws.com/openai/v1`. It takes either a
  request signed with SigV4 or a Bedrock API key as bearer. A short-term key (up to
  12 hours) is minted from the user's AWS identity by AWS's
  `aws-bedrock-token-generator` package
  ([Bedrock: chat completions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html),
  [aws-bedrock-token-generator](https://github.com/aws/aws-bedrock-token-generator-python)).

So all three end the same way: a short-lived token sent as a bearer token. They
differ in how the user gets one, and each cloud's own CLI already does that part,
with the browser sign-in, MFA, SSO and refresh its security team expects.

edgar's constraints: Core has no lines of code to spare, the dependency budget is
small (NFR-5), the import budget is strict (NFR-1), and there must be no hidden
host (PRV-15).

## Options

**A. OAuth in edgar, one flow per cloud.** Entra ID, Google and AWS IAM Identity
Center each have their own OAuth details, tenants and refresh rules. edgar would
need a registered client id for each, or would borrow the CLI's, which
impersonates Microsoft's, Google's or Amazon's tool (ADR-0043 rejects that for
GitHub). Several hundred lines of code, and three sets of terms to keep up with.

**B. The clouds' SDKs** (`azure-identity`, `google-auth`, `boto3`). They handle
every sign-in method, but they are large, slow to import, and one per cloud. SigV4
for Bedrock would come with `boto3`. It does not fit NFR-1 or NFR-5, nor Core's
budget.

**C. A command the user names, which prints a token.** `api_key_command` in a
`[providers.NAME]` block is an argv, run the way a command tool runs (never
through a shell). Its output is sent as a bearer token. The cloud's own CLI
does the sign-in. About 35 lines of code, no dependency, and it works for any
provider that takes a bearer token, not only these three.

## Decision

**C** [PRV-20], in Core.

- **Where the credential comes from, in order:**
  1. the key in `api_key_env`, if it is set, sent the way the provider's row says;
  2. otherwise `api_key_command`, if the block names one: edgar runs it and
     sends its output as `Authorization: Bearer`, even for Azure, whose keys go
     in an `api-key` header;
  3. otherwise the usual error naming the variable, with a hint that now names
     `api_key_command` too.
- **When it runs.** Once when the provider is resolved, so a lapsed sign-in
  fails before any request. Then again for any request made when the token is
  more than ten minutes old, so a long REPL session outlives the clouds'
  one-hour tokens. Its whole stdout, trimmed, is the token. It gets 60 seconds to
  finish.
- **How it runs.** Directly, never through a shell. `shutil.which` finds the
  program, so `az.cmd` works on Windows (NFR-6). A failure, a missing program or
  empty output is a `ConfigError` quoting the last line of the command's stderr,
  with the hint "sign in with the cloud's own CLI first: az login, gcloud auth
  login, aws sso login".
- **User config only.** A project's `.edgar/config.toml` that names
  `api_key_command` fails to load. A repository you clone must not choose the
  program that mints your credential, and provider resolution happens before
  the `--no-project-exec` and `edgar trust` checks (PERM-13) could apply. The
  user's config is already trusted: the user wrote it.
- **Where the token lives.** In memory only, in the adapter. It is never written
  to disk and never in a `repr`, the transcript, events or logs, the same as a
  key from the environment (CFG-6).
- **The hosts.** Only the `base_url` the user configured. The command talks to
  its own cloud, which the user chose by naming it (PRV-15).

The Cookbook has blocks to copy for Azure, Vertex AI and Bedrock.

## Consequences

- CFG-6 now reads: secrets come from the environment, from the OS keyring (the
  `keyring` extra), or from a command the user names in user config.
- 35 lines of code, in `providers/quirks.py`, `providers/http.py` and the
  config loader. Core had 34 to spare, so the endpoint hint in `connect` was
  shortened by a line, and Core now stands at exactly 5,000 lines of code.
- The command is trusted like the user's own shell: it runs with the user's
  rights, from the user's own config. It is not a tool the model can call.
- Anything that sends a bearer token works the same way: an internal gateway, or
  a proxy with its own `token` command.
- **Bedrock with SigV4** (signed requests rather than a bearer key) is not
  supported. AWS's short-term API key covers the same identities. If Bedrock ever
  drops API keys, SigV4 belongs in a v1 provider plugin (PRV-14), not in Core.
- **Bedrock's Anthropic models** on Bedrock's own Messages route, and Vertex's
  Anthropic models on `rawPredict`, need the Anthropic adapter to take another
  URL shape. They are not in this change. Claude reaches the OpenAI-compatible
  endpoints only where the cloud serves it there.

## Rejected alternatives

**A** would be worth it only if one of the CLIs stopped printing tokens. All three
document that command as a supported way to get one.

**B** is the right answer for a provider plugin written for one cloud. The
entry point (PRV-14) already allows one, outside Core's budget.

**Reading the token from a file** a helper refreshes was considered. It adds a
second process for the user to keep running, and a secret on disk.
