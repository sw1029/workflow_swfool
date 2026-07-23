# Root Authorization Host Contract

## Contents

1. Trust boundary
2. Fixed storage and wire contracts
3. Administration
4. Interactive signing
5. Publication and revocation
6. Validation checklist

## Trust boundary

Use the host-local administrator and signer only for ordinary S3 exact-plan root
authorization. Keep both modules outside the general `workflow authority` CLI.
Treat `agent_managed_local_bootstrap` as an interface and operating-procedure
boundary, not as independent isolation from another process running under the same
OS user. The `host_user_signed_exact_plan` wire value is retained for compatibility;
it does not prove a separate Unix account, keyring, HSM, or hardware boundary.

Do not pass a private key or passphrase through argv, environment variables,
stdout/stderr, exceptions, receipts, workspace `.task` artifacts, or model-visible
JSON. Do not copy or back up secret material automatically. `.gitignore` is an
accident-prevention layer, not a custody boundary.

Install the optional dependency before administration or signing:

```bash
python3 -m pip install 'cryptography>=44'
```

The ordinary verifier remains pure Python and must fail closed when the registry is
missing, empty, unsafe, non-canonical, or has no matching active key.

## Fixed storage and wire contracts

Derive `$CODEX_HOME` from the installed
`manage-agent-authority/scripts/manage_agent_authority` module. Do not accept a
caller-selected storage root. Store material under:

```text
$CODEX_HOME/root-authorization/
├── private/<key-id>.root-authorization-private.pem
├── public/<key-id>.root-authorization-public.pem
├── passphrases/<key-id>.root-authorization-passphrase
├── receipts/<key-id>.json
└── outbox/<evidence-id>.json
```

Require the store and subdirectories to be real, current-user-owned `0700`
directories. Require private, public, passphrase, receipt, and outbox files to be
real, current-user-owned `0600` files. Refuse symlinks, pre-existing provisioning
targets, wrong ownership, and group/world-writable authority paths.

Generate RSA-3072 keys with public exponent 65537. Serialize private keys as
passphrase-encrypted PKCS#8 PEM and public keys as SPKI PEM. Generate at least 48
bytes of URL-safe passphrase entropy internally. Derive:

```text
key-id = root-rsa-sha256-<sha256(SPKI-DER)>
issuer = local-agent-managed-root-authorizer
algorithm = rsassa-pkcs1-v1_5-sha256
```

Keep the existing trust-registry v1 schema and root evidence/grant schemas
unchanged. Render registry keys sorted by key ID and render the registry as compact,
sorted UTF-8 JSON with one terminal LF. Never add private custody data to it.

## Administration

Set the installed scripts directory on `PYTHONPATH`, then invoke the isolated
module:

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
AUTHORITY_PY="$SKILLS_ROOT/manage-agent-authority/scripts"

PYTHONPATH="$AUTHORITY_PY" python3 -P -m \
  manage_agent_authority.root_authority_admin status

PYTHONPATH="$AUTHORITY_PY" python3 -P -m \
  manage_agent_authority.root_authority_admin provision \
  --expected-registry-sha256 <digest-or-absent>

PYTHONPATH="$AUTHORITY_PY" python3 -P -m \
  manage_agent_authority.root_authority_admin register-public-key \
  --public-key /absolute/path/to/key.pem \
  --issuer <issuer-id> \
  --expected-registry-sha256 <digest-or-absent>

PYTHONPATH="$AUTHORITY_PY" python3 -P -m \
  manage_agent_authority.root_authority_admin revoke-public-key \
  --key-id <key-id> \
  --reason <reason-code> \
  --expected-registry-sha256 <digest>
```

Use the exact digest returned by `status`. Use `absent` only when the registry is
actually absent. The shipped empty registry has a real digest and requires that
digest. Registry mutation must hold the fixed adjacent lock, reread stable bytes
under 64 KiB, compare the expected SHA-256, write through a same-directory temporary
file, fsync the file, atomically replace, fsync the directory, and verify the final
digest.

`provision` generates, encrypts, pair-checks, sign/verifies, and registers one key.
It records only public identity, CAS digests, file paths/modes, custody mode, and the
same-UID limitation. `register-public-key` derives modulus, exponent, SPKI
fingerprint, and key ID from PEM; never accept caller-authored modulus JSON.

Treat exact active registration replay as a no-op after CAS verification. Refuse a
key-ID collision, duplicate SPKI under a different ID, issuer change, revoked-key
reactivation, or a second active key. Use `--rotation-overlap` only for deliberate
key rotation; it permits a second active key without revoking the first.

## Interactive signing

Prepare the exact producer CAS plan through the ordinary workflow, then invoke:

```bash
PYTHONPATH="$AUTHORITY_PY" python3 -P -m \
  manage_agent_authority.root_authorization_signer approve-root-plan \
  --workspace /absolute/workspace/root \
  --approval-plan-ref .task/authorization/root_approval_plans/sha256/<sha>.json \
  --approval-plan-sha256 <sha256> \
  --key-id <key-id>
```

The signer reopens and re-renders the producer plan. It displays only the plan
fingerprint, prepared/expiry times, grant count, and bounded holder/session/task,
capability, operation, subject, risk, cardinality, and budget projections. Approve
only by typing the following exact text on `/dev/tty`:

```text
APPROVE ROOT PLAN <approval-plan-sha256>
```

Do not add `--yes`, stdin approval, non-interactive bypass, private-key, passphrase,
registry, issuer, audience, `approved`, signature, or decision-time options.

After confirmation, capture UTC once. Derive authorization/evidence IDs from the
plan binding, key ID, absolute workspace identity, and that decision time. Render
the unsigned evidence as compact sorted JSON plus LF, sign it with RSA PKCS#1 v1.5
and SHA-256, check the encrypted private key against both stored public PEM and the
active registry entry, and self-verify through the ordinary verifier.

Write the signed envelope once to the fixed outbox with `O_EXCL` and mode `0600`.
Emit only the outbox path, evidence SHA-256, key ID, and exact plan binding on
stdout. The signer must not change the registry, prepare a plan, publish evidence,
compile a decision seed, or materialize a grant.

## Publication and revocation

Pass the signed outbox file to
`workflow authority publish-root-authorization-evidence`. That command reopens the
plan, verifies the signature against the active registry, publishes verified bytes
to workspace CAS, and returns only the binding. Continue with
`compile-root-decision-seed` and `materialize-plan-bound-root-grant` only when the
current task explicitly authorizes those effects.

Revocation requires an exact registry digest and exact `/dev/tty` confirmation:

```text
REVOKE <key-id> AND INVALIDATE EXISTING EVIDENCE
```

Revocation changes `active` to `revoked`; it never deletes key material and never
offers automatic reactivation. Under current verifier semantics, future
revalidation of evidence signed by that key fails, including evidence created
before revocation. Rotate by overlapping the new active key, moving signers to it,
then explicitly revoking the old key.

## Validation checklist

- Verify encrypted PKCS#8, correct/wrong passphrase behavior, public/private match,
  RSA size/exponent, self-signature, ownership, modes, and secret-free failures.
- Verify missing/symlink/pre-existing targets and partial-failure cleanup.
- Verify initial registration, exact replay, stale CAS, collision, duplicate SPKI,
  concurrent writers, non-canonical registry input, atomic replacement,
  revocation, and reactivation refusal.
- Verify exact plan reopening, expiry/tamper rejection, inactive or mismatched key,
  exact TTY confirmation, non-TTY rejection, outbox collision, canonical signing,
  and ordinary verifier self-check.
- Run a temporary-key prepare → sign → publish → compile → materialize integration
  path. Never use the live key for that test.
- Verify both repositories ignore sentinel private, public, passphrase, registry,
  and lock files while leaving signed evidence and `.task` CAS auditable.
- Run focused and full pytest, Ruff, compileall, `git diff --check`,
  `quick_validate.py`, and the SKILL line/word limits before live provisioning.
