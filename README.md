# pyrad-server

`pyrad-server` is a **lab-grade RADIUS test server** built on top of
[`pyrad`](https://pypi.org/project/pyrad/).

It is designed for **development, testing, CI pipelines, and network labs**, where a
deterministic, configurable, and protocol-correct RADIUS implementation is required.

This project is **not intended to replace production-grade RADIUS servers** such as
FreeRADIUS, but to provide a controllable and inspectable environment for testing
clients, workflows, and integrations.

> [!NOTE]
> One of the use cases for this repository is end-to-end testing of the pyrad library in a fully reproducible devcontainer environment.

- [Features](#features)
- [Project Structure](#project-structure)
- [Installation (Development)](#installation-development)
- [Running the Server](#running-the-server)
- [Configuration](#configuration)
  - [Configuration Structure Overview](#configuration)
  - [Address Pools](#address-pools)
  - [Reply Definitions](#reply-definitions)
  - [Pool Match Rules](#pool-match-rules)
  - [Reply Match Rules](#reply-match-rules)
  - [Redis Dialog Storage](#redis-dialog-storage)
- [RADIUS Test Client](#radius-test-client)
  - [Client Debug Output](#client-debug-output)
- [Testing](#testing)
  - [E2E Testing for pyrad releases](#e2e-testing-for-pyrad-releases)
- [Development with VS Code Devcontainer](#development-with-vs-code-devcontainer)
- [License](#license)


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

The `pyrad-server` configuration is defined in a single YAML file and is organized into the following sections:

- **`address_pools`**
   Defines IPv4/IPv6 address pools used for dynamic address assignment.
- **`reply_definitions`**
   Predefined RADIUS replies (e.g. Access-Accept, Accounting-Response) with explicit response codes and attributes.
- **`pool_match_rules`**
   Rule-based mapping of incoming requests to address pools.
   Rules are evaluated in order (first match wins).
- **`reply_match_rules`**
   Determines which reply definition is selected for a given request, grouped by RADIUS packet type.
- **`redis_storage`**
   Configuration for storing and correlating RADIUS dialog state in Redis across authentication, accounting, and control flows.

---

### Address Pools

```yaml
address_pools:
  pool1:
    shuffle: false
    ipv4:
      - 10.0.0.0/24
  pool2:
    shuffle: false
    ipv4:
      - 10.0.1.0/24
```

Defines IP address pools that can be used for dynamic address assignment
(e.g. `Framed-IP-Address`).

---

### Reply Definitions

```yaml
reply_definitions:
  auth:
    ok1:
      code: 2
      attributes:
        Reply-Message: "OK for alice"
        Framed-IP-Address: "-> fromPool"
    ok2:
      code: 2
      attributes:
        Reply-Message: "OK for bob"
        Framed-IP-Address: "-> fromPool"

  acct:
    acct_ok:
      code: 5
      attributes: {}
```

---

### Pool Match Rules

```yaml
pool_match_rules:
  - pool1:
      - User-Name: "alice"
  - pool2:
      - User-Name: "bob"
```

---

### Reply Match Rules

```yaml
reply_match_rules:
  auth:
    - ok1:
        - User-Name: "alice"
    - ok2:
        - User-Name: "bob"

  acct:
    - acct_ok: []
```

---

### Redis Dialog Storage

```yaml
redis_storage:
  prefix: "pyrad-server::"
  auth:
    - Acct-Session-Id
  acct:
    - Acct-Session-Id
  coa:
    - Acct-Session-Id
  disc:
    - Acct-Session-Id
```

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

### E2E Testing for pyrad releases:

Once the devcontainer is established, it is possible to run the client pytest suite and monitor the RADIUS packets to and from the server using tcpdump.

```
vscode ➜ /workspaces/pyrad-server (main) $ pytest tests/tools/test_pyrad_test_client.py -vvv -s 
=== test session starts ============================================================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /workspaces/pyrad-server
configfile: pyproject.toml
plugins: anyio-4.12.1, cov-7.0.0
collected 3 items                                                                                                                           

tests/tools/test_pyrad_test_client.py::test_auth_request_receives_accept_and_reply_message PASSED
tests/tools/test_pyrad_test_client.py::test_acct_request_accounting_on PASSED
tests/tools/test_pyrad_test_client.py::test_acct_request_receives_accounting_response PASSED

===3 passed in 0.02s =============================================================
```

tcpdump monitoring:
```
vscode ➜ /workspaces/pyrad-server (main) $ sudo tcpdump -i lo -vvv 'udp port 1812 or udp port 1813'
tcpdump: listening on lo, link-type EN10MB (Ethernet), snapshot length 262144 bytes
04:04:26.763724 IP (tos 0x0, ttl 64, id 36268, offset 0, flags [DF], proto UDP (17), length 177)
    localhost.37268 > localhost.radius: [bad udp cksum 0xfeb0 -> 0x7b40!] RADIUS, length: 149
        Access-Request (1), id: 0x03, Authenticator: 7afe3cc8bb42f6da6c188f5508ef8353
          User-Name Attribute (1), length: 7, Value: alice
            0x0000:  616c 6963 65
          NAS-IP-Address Attribute (4), length: 6, Value: 192.168.1.10
            0x0000:  c0a8 010a
          NAS-Port Attribute (5), length: 6, Value: 1
            0x0000:  0000 0001
          NAS-Identifier Attribute (32), length: 20, Value: pytest server 0001
            0x0000:  7079 7465 7374 2073 6572 7665 7220 3030
            0x0010:  3031
          Acct-Session-Id Attribute (44), length: 19, Value: pytest:1769313866
            0x0000:  7079 7465 7374 3a31 3736 3933 3133 3836
            0x0010:  36
          User-Password Attribute (2), length: 18, Value: 
            0x0000:  395e 12df 27dc 4653 4435 e1c6 9e7a dc73
          Calling-Station-Id Attribute (31), length: 53, Value: test_auth_request_receives_accept_and_reply_message
            0x0000:  7465 7374 5f61 7574 685f 7265 7175 6573
            0x0010:  745f 7265 6365 6976 6573 5f61 6363 6570
            0x0020:  745f 616e 645f 7265 706c 795f 6d65 7373
            0x0030:  6167 65
04:04:26.764080 IP (tos 0x0, ttl 64, id 36269, offset 0, flags [DF], proto UDP (17), length 58)
    localhost.radius > localhost.37268: [bad udp cksum 0xfe39 -> 0x0ef4!] RADIUS, length: 30
        Access-Accept (2), id: 0x03, Authenticator: 841da7cc18db2dfe7c50ba0c82dcb880
          Reply-Message Attribute (18), length: 4, Value: OK
            0x0000:  4f4b
          Framed-IP-Address Attribute (8), length: 6, Value: 10.0.0.15
            0x0000:  0a00 000f
```


## Development with VS Code Devcontainer

This repository includes a ready-to-use VS Code Devcontainer setup for reproducible
development and lab environments.

Features:

- Ubuntu-based development container
- Redis running inside the container
- E2E Testing for pyrad library
- RADIUS UDP ports exposed (1812 / 1813)
- REST API exposed on port 5711
- Persistent shell history

Open the repository in VS Code and select:
“Reopen in Container”

## License

MIT License.  
See `LICENSE.rst` for details.
