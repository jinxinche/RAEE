# Evidence Contracts: a 60-second walkthrough

Use the commands below in a scratch project. The Python command is a dummy successful check: **it is NOT a genuine integration or E2E test**. It shows the difference between a command receipt and behavior evidence.

```bash
mkdir scratch-raee && cd scratch-raee
printf 'print("hello")\n' > app.py
raee-lite check
raee-lite add "The login button works in the browser"  # R1
raee-lite plan  # suggests E2E based on a keyword; does not prove anything
raee-lite expect --for R1 --kind e2e
raee-lite check --ci     # fails: missing E2E-labelled receipt
raee-lite run --for R1 --kind unit -- python -c 'print("passing unit")'
raee-lite check --ci     # still fails: unit does not stand in for E2E
```

To demonstrate the *mechanics* of recording a matching scope (still not actual coverage), one can execute a labelled check:

```bash
raee-lite run --for R1 --kind e2e -- python -c 'print("dummy receipt, not an e2e test")'
raee-lite check --ci      # may pass: receipt is current and exit code was zero
```

**Interpretation:** That successful exit is not evidence a browser was used. For real use, replace the dummy command with an actual targeted test. After editing `app.py`, `raee-lite status` marks the check stale. Inspect the report in `.raee/report.html`, `.raee/report.json` and `.raee/report.sarif`.

For privacy and security, execute unknown project scripts only after reviewing them and within an isolated environment; RAEE-Lite does not provide one.
