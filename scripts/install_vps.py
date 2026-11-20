#!/usr/bin/env python3
"""Install the isolated Nexus Atende project behind an existing Traefik."""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "nexus-atende-prod"
ORIGIN = "https://atende.nexusdataanalytics.tech"
ENV_FILE = ROOT / ".env.production"
STATE = ROOT / ".deploy"
ADMIN_FILE = STATE / "primeiro-acesso.txt"
ROTAFY_DOMAIN = "rotafy.nexusdataanalytics.tech"


def run(*args: str, input: str | None = None, stdout: BinaryIO | None = None) -> None:
    subprocess.run(args, cwd=ROOT, check=True, input=input, stdout=stdout, text=True, encoding="utf-8")


def output(*args: str, input: str | None = None) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, input=input, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def private_write(path: Path, value: str) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as file:
        file.write(value)


def create_environment(admin_email: str, openwa_url: str) -> None:
    runtime_password = secrets.token_hex(32)
    tenant_id = str(uuid4())
    private_write(ADMIN_FILE, f"Empresa Nexus: {tenant_id}\nE-mail: {admin_email}\nSenha: {secrets.token_urlsafe(24)}\n")
    variables = {
        "NEXUS_ATENDE_DB_PASSWORD": secrets.token_hex(32),
        "NEXUS_ATENDE_DATABASE_URL": f"postgresql+asyncpg://nexus_atende_runtime:{runtime_password}@postgres/nexus_atende",
        "NEXUS_ATENDE_PUBLIC_ORIGIN": ORIGIN,
        "NEXUS_ATENDE_CONFIG_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "NEXUS_ATENDE_OPENWA_BASE_URL": openwa_url,
        "NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID": tenant_id,
        "NEXUS_ATENDE_OPENWA_WEBHOOK_SECRET": secrets.token_hex(32),
    }
    private_write(ENV_FILE, "".join(f"{name}={value}\n" for name, value in variables.items()))


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def bootstrap(compose: tuple[str, ...], values: dict[str, str]) -> None:
    database = re.fullmatch(r"postgresql\+asyncpg://nexus_atende_runtime:([0-9a-f]{64})@postgres/nexus_atende",
                            values["NEXUS_ATENDE_DATABASE_URL"])
    if database is None:
        raise ValueError("A URL de runtime deve conservar o formato gerado pelo instalador.")
    tenant = str(UUID(values["NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID"]))
    psql = (*compose, "exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "nexus_atende")
    password = sql_string(database[1])
    run(*psql, input=f"""
        BEGIN;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_atende_runtime') THEN
                EXECUTE format('CREATE ROLE nexus_atende_runtime LOGIN INHERIT NOSUPERUSER NOBYPASSRLS IN ROLE nexus_atende_app PASSWORD %L', {password});
            END IF;
        END $$;
        INSERT INTO nexus_atende.tenants (id, name) VALUES ('{tenant}', 'Nexus') ON CONFLICT (id) DO NOTHING;
        COMMIT;
    """)
    admin = output(*psql, "-Atc", f"SELECT 1 FROM nexus_atende.users WHERE tenant_id = '{tenant}' AND role = 'admin' LIMIT 1")
    if admin:
        return
    company, email, initial_password = (line.split(": ", 1)[1] for line in ADMIN_FILE.read_text(encoding="utf-8").splitlines())
    if company != tenant or not re.fullmatch(r"[^\s@]+@[^\s@]+", email):
        raise ValueError("Dados do administrador inicial incompatíveis com a empresa configurada.")
    hashed = output(*compose, "run", "--rm", "--no-deps", "-T", "--label", "traefik.enable=false", "api", "python", "-c",
                    "import sys; from src.services.passwords import hash_password; print(hash_password(sys.stdin.read()))",
                    input=initial_password)
    run(*psql, input=f"""
        INSERT INTO nexus_atende.users (tenant_id, name, email, password_hash, role)
        VALUES ('{tenant}', 'Administrador Nexus', {sql_string(email)}, {sql_string(hashed)}, 'admin');
    """)


def public_check() -> bool:
    last_error = "resposta inesperada"
    for attempt in range(5):
        try:
            headers = {"User-Agent": "Nexus-Atende-Installer/1.0", "Accept": "application/json"}
            with urllib.request.urlopen(urllib.request.Request(f"{ORIGIN}/api/v1/health", headers=headers), timeout=5) as api:
                health = json.load(api)
                if not isinstance(health, dict) or health.get("status") != "ok":
                    raise ValueError("a API pública não retornou o status esperado")
            with urllib.request.urlopen(urllib.request.Request(ORIGIN, headers={**headers, "Accept": "text/html"}), timeout=5) as web:
                if "text/html" not in web.headers.get("Content-Type", ""):
                    raise ValueError("o painel público não retornou HTML")
            return True
        except HTTPError as error:
            last_error = f"HTTP {error.code}"
        except URLError as error:
            last_error = str(error.reason)
        except (OSError, ValueError) as error:
            last_error = str(error)
        if attempt < 4:
            time.sleep(3)
    print(f"Aviso: serviços locais saudáveis, checagem HTTPS a partir da VPS inconclusiva ({last_error}).", file=sys.stderr)
    return False


def choose(flag: str, explicit: str | None, candidates: set[str]) -> str:
    candidates.discard("")
    if explicit:
        value = explicit
    elif len(candidates) == 1:
        value = next(iter(candidates))
    elif sys.stdin.isatty():
        choices = f" ({', '.join(sorted(candidates))})" if candidates else ""
        value = input(f"{flag}{choices}: ").strip()
    else:
        raise ValueError(f"Não foi possível detectar {flag}. Opções: {', '.join(sorted(candidates)) or 'nenhuma'}.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", value):
        raise ValueError(f"Valor inválido para {flag}.")
    return value


def detect_routing(args: argparse.Namespace) -> dict[str, str]:
    running_ids = output("docker", "ps", "-q").splitlines()
    containers = json.loads(output("docker", "inspect", "--type", "container", *running_ids)) if running_ids else []
    by_name = {container["Name"].lstrip("/"): container for container in containers}
    proxies = {name for name, container in by_name.items() if "traefik" in container["Config"]["Image"].lower()}
    name = choose("--traefik-container", args.traefik_container, proxies)
    if name not in by_name:
        raise ValueError("O container Traefik informado não está em execução.")
    proxy = by_name[name]
    networks = proxy["NetworkSettings"]["Networks"]
    flags = proxy["Config"].get("Cmd") or []
    if any(flag.lower() in {"--providers.docker.swarmmode=true", "--providers.docker=false"}
           or flag.lower().startswith("--providers.swarm") and not flag.lower().endswith("=false") for flag in flags):
        raise ValueError("O instalador exige o provider Docker do Traefik, com uma rede bridge.")

    entries: set[str] = set()
    resolvers: set[str] = set()
    route_networks: set[str] = set()
    for container in containers:
        labels = container["Config"].get("Labels") or {}
        for key, rule in labels.items():
            if not key.startswith("traefik.http.routers.") or not key.endswith(".rule") or ROTAFY_DOMAIN not in rule:
                continue
            route = key[:-len(".rule")]
            entries.update(entry.strip() for entry in labels.get(route + ".entrypoints", "").split(","))
            resolvers.add(labels.get(route + ".tls.certresolver", ""))
            shared = set(networks) & set(container["NetworkSettings"]["Networks"])
            selected = labels.get("traefik.docker.network")
            route_networks.update({selected} if isinstance(selected, str) and selected in shared else shared)
    flagged_entries: set[str] = set()
    flagged_resolvers: set[str] = set()
    for flag in flags:
        match = re.fullmatch(r"--entrypoints\.([^.]+)\.address=.*:443(?:/tcp)?", flag, re.IGNORECASE)
        if match:
            flagged_entries.add(match[1])
        match = re.match(r"--certificatesresolvers\.([^.]+)\.", flag, re.IGNORECASE)
        if match:
            flagged_resolvers.add(match[1])
    network = choose("--network", args.network, route_networks or set(networks))
    if network not in networks:
        raise ValueError(f"O Traefik não pertence à rede {network}.")
    metadata = json.loads(output("docker", "network", "inspect", network))[0]
    if metadata.get("Driver") != "bridge" or metadata.get("Internal"):
        raise ValueError("Informe uma rede bridge do Traefik com saída de rede.")
    return {
        "NEXUS_DEPLOY_PROXY_IP": str(ipaddress.ip_address(networks[network].get("IPAddress", ""))),
        "NEXUS_DEPLOY_NETWORK": network,
        "NEXUS_DEPLOY_ENTRYPOINT": choose("--entrypoint", args.entrypoint, entries - {""} or flagged_entries),
        "NEXUS_DEPLOY_RESOLVER": choose("--resolver", args.resolver, resolvers - {""} or flagged_resolvers),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traefik-container")
    parser.add_argument("--network")
    parser.add_argument("--entrypoint")
    parser.add_argument("--resolver")
    parser.add_argument("--admin-email")
    parser.add_argument("--openwa-url", default="", help="Endereço HTTPS terminado em /api, usado na primeira instalação")
    parser.add_argument("--skip-public-check", action="store_true", help="Validar apenas a saúde interna dos serviços")
    args = parser.parse_args()

    if args.openwa_url and not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?/api/?", args.openwa_url):
        raise ValueError("Endereço OpenWA inválido, use uma URL HTTPS terminada em /api.")
    os.environ.update(detect_routing(args))
    for name in tuple(os.environ):
        if name.startswith("NEXUS_ATENDE_"):
            del os.environ[name]
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    lock = STATE / "install.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError("Já existe uma instalação em andamento ou um lock pendente em .deploy/install.lock.") from None
    try:
        volume = f"{PROJECT}_postgres_data"
        has_database = volume in output("docker", "volume", "ls", "--filter", f"name={volume}", "--format", "{{.Name}}").splitlines()
        if not ENV_FILE.exists():
            if has_database or ADMIN_FILE.exists():
                raise RuntimeError("A instalação anterior tem dados ou credenciais. Restaure .env.production antes de continuar.")
            email = args.admin_email or (input("E-mail do administrador: ").strip() if sys.stdin.isatty() else "")
            if not re.fullmatch(r"[a-zA-Z0-9_+.%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", email):
                raise ValueError("Informe --admin-email com um e-mail válido na primeira instalação.")
            create_environment(email.lower(), args.openwa_url)
        values = dict(line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        if values.get("NEXUS_ATENDE_PUBLIC_ORIGIN") != ORIGIN:
            raise ValueError(f"A origem pública em {ENV_FILE.name} deve ser {ORIGIN}.")
        compose = ("docker", "compose", "--project-name", PROJECT, "--env-file", str(ENV_FILE),
                   "-f", "compose.yaml", "-f", "compose.production.yaml", "--profile", "app", "--profile", "web")
        run(*compose, "config", "--quiet")
        run(*compose, "build", "api", "web")
        run(*compose, "up", "-d", "--wait", "postgres")
        if has_database:
            backup = STATE / f"banco-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.dump"
            partial = backup.with_suffix(".partial")
            with partial.open("xb") as file:
                run(*compose, "exec", "-T", "postgres", "pg_dump", "-U", "postgres", "-Fc", "nexus_atende", stdout=file)
            partial.rename(backup)
        psql = (*compose, "exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "nexus_atende")
        exists = output(*psql, "-Atc", "SELECT to_regclass('public.alembic_version') IS NOT NULL")
        revision = output(*psql, "-Atc", "SELECT version_num FROM public.alembic_version") if exists == "t" else ""
        if revision and not re.fullmatch(r"[0-9]{4}_[a-z0-9_]+", revision):
            raise ValueError("Revisão Alembic inesperada.")
        target = f"{revision}:head" if revision else "head"
        migration = output(*compose, "run", "--rm", "--no-deps", "-T", "--label", "traefik.enable=false", "api", "alembic", "upgrade", target, "--sql")
        if migration:
            run(*psql, input=migration + "\n")
        bootstrap(compose, values)
        run(*compose, "up", "-d", "--wait", "--wait-timeout", "120", "api", "web", "worker")
        if not args.skip_public_check:
            public_check()
        print(f"Nexus Atende instalado em {ORIGIN}. Primeiro acesso: {ADMIN_FILE}")
    finally:
        lock.rmdir()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Instalação interrompida: {error}")
