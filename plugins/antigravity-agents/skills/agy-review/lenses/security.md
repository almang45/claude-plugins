Find ways an attacker, or any untrusted input, can read, change or break what it should not.

- Injection: SQL and NoSQL, shell, template, header and log injection; strings built by hand
  where a parameterized API exists.
- Authentication and authorization: missing or bypassable checks, IDOR, a permission checked
  on the wrong object, trust in client-supplied identity or roles.
- Input handling: path traversal, SSRF, open redirects, unsafe deserialization, XXE, regex
  denial of service, unbounded request or upload sizes.
- Secrets and data: credentials, tokens or keys in code, config, logs, error messages or test
  fixtures; personal data written to logs; weak or misused crypto (static IVs, ECB, fast hashes
  for passwords, non-cryptographic randomness for tokens); TLS verification turned off.
- Infrastructure as code: containers running as root, privileged pods or hostPath mounts,
  a missing securityContext, wildcard RBAC, secrets in plain manifests or environment
  variables, public buckets, over-broad IAM.
- Supply chain: new dependencies that are unpinned, typo-squatted or fetched over plain HTTP;
  CI actions pinned by tag instead of commit SHA; scripts piped from curl.

Name the attacker's input and what it gains them. Leave out issues with no reachable path from
untrusted input.
