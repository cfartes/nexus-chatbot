from getpass import getpass
from hashlib import scrypt
from secrets import compare_digest, token_bytes


def _derive(password: str, salt: bytes) -> bytes:
    return scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024**2)


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    return f"scrypt${salt.hex()}${_derive(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, encoded_salt, encoded_hash = stored.split("$")
        salt, expected = bytes.fromhex(encoded_salt), bytes.fromhex(encoded_hash)
    except ValueError:
        return False
    return algorithm == "scrypt" and len(salt) == 16 and compare_digest(_derive(password, salt), expected)


if __name__ == "__main__":
    password = getpass("Senha do operador: ")
    if not 12 <= len(password) <= 128 or password != getpass("Repita a senha: "):
        raise SystemExit("As senhas devem coincidir e ter entre 12 e 128 caracteres.")
    print(hash_password(password))
