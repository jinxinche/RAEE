# A 60-second demo

In a disposable directory, create `app.py` and `tests/test_app.py` with a green test that does not cover the requested feature:

```bash
mkdir -p demo/tests && cd demo
printf "def signup(email):\n    return True\n" > app.py
printf "def test_smoke():\n    assert 1 + 1 == 2\n" > tests/test_app.py
raee-lite check --run
```

The existing test can pass, but this does not prove signup correctness. After the check:

```bash
raee-lite add "Signup rejects invalid email addresses"
raee-lite status  # requirement is UNTESTED, despite observed auto test pass
printf "# TODO validation\n" >> app.py
raee-lite status  # old test evidence becomes STALE
```

The example intentionally uses an inadequate test to demonstrate the boundary. It is not a recommendation for how to write tests. A real verification should add tests that cover the specified requirement.
