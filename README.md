# pyrad-server
# pyrad-server

`pyrad-server` is a **lab-grade RADIUS test server** built on top of
[`pyrad`](https://pypi.org/project/pyrad/).

It is designed for **development, testing, CI pipelines, and network labs**, where a
deterministic, configurable, and protocol-correct RADIUS implementation is required.

This project is **not intended to replace production-grade RADIUS servers** such as
FreeRADIUS, but to provide a controllable and inspectable environment for testing
clients, workflows, and integrations.

---

## Features

- Real RADIUS protocol over UDP (Auth + Acct)
- Deterministic configuration via YAML
- Rule-based matching (auth/accounting)
- Address pool management (IPv4 / IPv6 / delegated IPv6)
- Redis-backed dialog storage
- FastAPI-based REST API
- Asyncio-based runtime (no aiomisc entrypoint)
- Integrated **test RADIUS client** for labs and CI
- High test coverage (unit + integration tests)

---

## Project Structure

```text
src/
└─ pyrad_server/
   ├─ cli.py
   ├─ api/
   ├─ config/
   ├─ radius/
   ├─ udp/
   ├─ storage/
   └─ tools/
      └─ pyrad_test_client.py
```

---

## Installation (Development)

```bash
git clone <repo>
cd pyrad-server
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

---

## Running the Server

```bash
pyrad-server serve \
  --with-radius \
  --config-path conf/test-config.yml \
  --dictionary-path conf/dictionary \
  --secret testsecret \
  --rest-port 4711 \
  --auth-port 1812 \
  --acct-port 1813 \
  --redis-host 127.0.0.1 \
  --redis-port 6379
```

---

## Configuration

See `conf/test-config.yml` for a minimal example.

---

## Test Client

The project includes an integrated **RADIUS test client** intended for labs and CI.

---

## Testing

```bash
pytest
pytest -m integration
```

---

## License

See `LICENSE.rst`.
