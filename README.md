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

- Real RADIUS protocol over UDP (Authentication + Accounting)
- Fully deterministic configuration of **complete RADIUS response contents** via YAML,
  including explicit control over all response attributes
- Rule-based request matching for authentication and accounting flows
- Address pool management (IPv4 / IPv6 / delegated IPv6)
- Redis-backed dialog storage for request/response inspection
- FastAPI-based REST API for runtime inspection and control (under development)
- Asyncio-native runtime (no aiomisc entrypoint)
- Integrated **RADIUS test client** for labs and CI pipelines

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

Configuration is provided via YAML.  
See `conf/test-config.yml` for a minimal working example.

---

## RADIUS Test Client

The project includes an integrated RADIUS test client intended for labs, development, and CI pipelines.
The test client is currently used in pytest-based integration tests and is designed to allow full control over RADIUS requests, including explicit setting of all request attributes, to enable precise and reproducible test scenarios.

---

### Client Debug Output

Enable full request/response logging:

```bash
pytest tests/tools/test_pyrad_test_client.py \
  -s \
  --log-cli-level=DEBUG \
  --log-cli-format="%(levelname)s %(name)s: %(message)s"
```

Example output:

```text
DEBUG pyrad_server.test_client: → Access-Request to 127.0.0.1:1812
DEBUG pyrad_server.test_client:     user_name = 'alice'
DEBUG pyrad_server.test_client: ⏱ Access-Request RTT: 1.90 ms
DEBUG pyrad_server.test_client: ← Access-Accept from 127.0.0.1:1812
DEBUG pyrad_server.test_client:     Reply-Message = 'OK'
DEBUG pyrad_server.test_client:     Framed-IP-Address = '10.0.0.42'
```

---

## Testing

Run all tests:

```bash
pytest
```

---


## Development with VS Code Devcontainer

This repository includes a ready-to-use VS Code Devcontainer setup for reproducible
development and lab environments.

Features:

- Ubuntu-based development container
- Redis running inside the container
- RADIUS UDP ports exposed (1812 / 1813)
- REST API exposed on port 5711
- Persistent shell history
- Identical environment for local development and CI

Open the repository in VS Code and select:
“Reopen in Container”

## License

MIT License.  
See `LICENSE.rst` for details.
